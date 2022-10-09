# -*- coding: utf-8 -*-
"""Text parser plugin for Windows Firewall Log files."""

import pytz

import pyparsing

from dfdatetime import time_elements as dfdatetime_time_elements

from plaso.containers import events
from plaso.containers import time_events
from plaso.lib import definitions
from plaso.lib import errors
from plaso.parsers import text_parser
from plaso.parsers.text_plugins import interface


class WinFirewallEventData(events.EventData):
  """Windows Firewall event data.

  Attributes:
    action (str): action taken.
    protocol (str): IP protocol.
    source_ip (str): source IP address.
    dest_ip (str): destination IP address.
    source_port (int): TCP or UDP source port.
    dest_port (int): TCP or UDP destination port.
    size (int): size of ???
    flags (str): TCP flags.
    tcp_seq (int): TCP sequence number.
    tcp_ack (int): TCP ACK ???
    tcp_win (int): TCP window size ???
    icmp_type (int): ICMP type.
    icmp_code (int): ICMP code.
    info (str): ???
    path (str): ???
  """

  DATA_TYPE = 'windows:firewall:log_entry'

  def __init__(self):
    """Initializes event data."""
    super(WinFirewallEventData, self).__init__(data_type=self.DATA_TYPE)
    self.action = None
    self.dest_ip = None
    self.dest_port = None
    self.flags = None
    self.icmp_code = None
    self.icmp_type = None
    self.info = None
    self.path = None
    self.protocol = None
    self.size = None
    self.source_ip = None
    self.source_port = None
    self.tcp_ack = None
    self.tcp_seq = None
    self.tcp_win = None


class WinFirewallLogTextPlugin(interface.TextPlugin):
  """Text parser plugin for Windows Firewall Log files."""

  NAME = 'winfirewall'
  DATA_FORMAT = 'Windows Firewall log file'

  ENCODING = 'ascii'

  # TODO: Add support for custom field names. Currently this parser only
  # supports the default fields, which are:
  #   date time action protocol src-ip dst-ip src-port dst-port size
  #   tcpflags tcpsyn tcpack tcpwin icmptype icmpcode info path

  _BLANK = pyparsing.Suppress(pyparsing.Literal('-'))

  _WORD = (
      pyparsing.Word(pyparsing.alphanums) |
      pyparsing.Word(pyparsing.alphanums + '-', min=2) |
      _BLANK)

  _INTEGER = pyparsing.Word(pyparsing.nums).setParseAction(
      text_parser.ConvertTokenToInteger) | _BLANK

  _TWO_DIGITS = pyparsing.Word(pyparsing.nums, exact=2).setParseAction(
      text_parser.PyParseIntCast)

  _FOUR_DIGITS = pyparsing.Word(pyparsing.nums, exact=4).setParseAction(
      text_parser.PyParseIntCast)

  _DATE_TIME = pyparsing.Group(
      _FOUR_DIGITS.setResultsName('year') + pyparsing.Suppress('-') +
      _TWO_DIGITS.setResultsName('month') + pyparsing.Suppress('-') +
      _TWO_DIGITS.setResultsName('day_of_month') +
      _TWO_DIGITS.setResultsName('hours') + pyparsing.Suppress(':') +
      _TWO_DIGITS.setResultsName('minutes') + pyparsing.Suppress(':') +
      _TWO_DIGITS.setResultsName('seconds')).setResultsName('date_time')

  _IP_ADDRESS = (
      pyparsing.pyparsing_common.ipv4_address |
      pyparsing.pyparsing_common.ipv6_address | _BLANK)

  _PORT_NUMBER = pyparsing.Word(pyparsing.nums, max=6).setParseAction(
      text_parser.ConvertTokenToInteger) | _BLANK

  _COMMENT_LINE = pyparsing.Literal('#') + pyparsing.SkipTo(pyparsing.LineEnd())

  _LOG_LINE = (
      _DATE_TIME +
      _WORD.setResultsName('action') +
      _WORD.setResultsName('protocol') +
      _IP_ADDRESS.setResultsName('source_ip') +
      _IP_ADDRESS.setResultsName('dest_ip') +
      _PORT_NUMBER.setResultsName('source_port') +
      _PORT_NUMBER.setResultsName('dest_port') +
      _INTEGER.setResultsName('size') +
      _WORD.setResultsName('flags') +
      _INTEGER.setResultsName('tcp_seq') +
      _INTEGER.setResultsName('tcp_ack') +
      _INTEGER.setResultsName('tcp_win') +
      _INTEGER.setResultsName('icmp_type') +
      _INTEGER.setResultsName('icmp_code') +
      _WORD.setResultsName('info') +
      _WORD.setResultsName('path'))

  _LINE_STRUCTURES = [
      ('comment', _COMMENT_LINE),
      ('logline', _LOG_LINE)]

  _SUPPORTED_KEYS = frozenset([key for key, _ in _LINE_STRUCTURES])

  def __init__(self):
    """Initializes a text parser plugin."""
    super(WinFirewallLogTextPlugin, self).__init__()
    self._software = None
    self._use_local_timezone = False
    self._version = None

  def _ParseCommentRecord(self, structure):
    """Parse a comment and store appropriate attributes.

    Args:
      structure (pyparsing.ParseResults): parsed log line.
    """
    comment = structure[1]
    if comment.startswith('Version'):
      _, _, self._version = comment.partition(':')
    elif comment.startswith('Software'):
      _, _, self._software = comment.partition(':')
    elif comment.startswith('Time'):
      _, _, time_format = comment.partition(':')
      if 'local' in time_format.lower():
        self._use_local_timezone = True

  def _ParseLogLine(self, parser_mediator, structure):
    """Parse a single log line and produce an event object.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      structure (pyparsing.ParseResults): structure of tokens derived from
          a line of a text file.
    """
    # Ensure time_elements_tuple is not a pyparsing.ParseResults otherwise
    # copy.deepcopy() of the dfDateTime object will fail on Python 3.8 with:
    # "TypeError: 'str' object is not callable" due to pyparsing.ParseResults
    # overriding __getattr__ with a function that returns an empty string when
    # named token does not exist.
    time_elements_structure = structure.get('date_time', None)

    try:
      year, month, day_of_month, hours, minutes, seconds = (
          time_elements_structure)

      date_time = dfdatetime_time_elements.TimeElements(time_elements_tuple=(
          year, month, day_of_month, hours, minutes, seconds))
      date_time.is_local_time = True

    except (TypeError, ValueError):
      parser_mediator.ProduceExtractionWarning(
          'invalid date time value: {0!s}'.format(time_elements_structure))
      return

    event_data = WinFirewallEventData()
    event_data.action = self._GetValueFromStructure(structure, 'action')
    event_data.dest_ip = self._GetValueFromStructure(structure, 'dest_ip')
    event_data.dest_port = self._GetValueFromStructure(structure, 'dest_port')
    event_data.flags = self._GetValueFromStructure(structure, 'flags')
    event_data.icmp_code = self._GetValueFromStructure(structure, 'icmp_code')
    event_data.icmp_type = self._GetValueFromStructure(structure, 'icmp_type')
    event_data.info = self._GetValueFromStructure(structure, 'info')
    event_data.path = self._GetValueFromStructure(structure, 'path')
    event_data.protocol = self._GetValueFromStructure(structure, 'protocol')
    event_data.size = self._GetValueFromStructure(structure, 'size')
    event_data.source_ip = self._GetValueFromStructure(structure, 'source_ip')
    event_data.source_port = self._GetValueFromStructure(
        structure, 'source_port')
    event_data.tcp_ack = self._GetValueFromStructure(structure, 'tcp_ack')
    event_data.tcp_seq = self._GetValueFromStructure(structure, 'tcp_seq')
    event_data.tcp_win = self._GetValueFromStructure(structure, 'tcp_win')

    if self._use_local_timezone:
      time_zone = parser_mediator.timezone
    else:
      time_zone = pytz.UTC

    event = time_events.DateTimeValuesEvent(
        date_time, definitions.TIME_DESCRIPTION_WRITTEN, time_zone=time_zone)
    parser_mediator.ProduceEventWithEventData(event, event_data)

  def _ParseRecord(self, parser_mediator, key, structure):
    """Parses a log record structure and produces events.

    This function takes as an input a parsed pyparsing structure
    and produces an EventObject if possible from that structure.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfVFS.
      key (str): name of the parsed structure.
      structure (pyparsing.ParseResults): tokens from a parsed log line.

    Raises:
      ParseError: when the structure type is unknown.
    """
    if key not in self._SUPPORTED_KEYS:
      raise errors.ParseError(
          'Unable to parse record, unknown structure: {0:s}'.format(key))

    if key == 'comment':
      self._ParseCommentRecord(structure)

    elif key == 'logline':
      self._ParseLogLine(parser_mediator, structure)

  def CheckRequiredFormat(self, parser_mediator, text_file_object):
    """Check if the log record has the minimal structure required by the plugin.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfVFS.
      text_file_object (dfvfs.TextFile): text file.

    Returns:
      bool: True if this is the correct parser, False otherwise.
    """
    try:
      line = self._ReadLineOfText(text_file_object)
    except UnicodeDecodeError:
      return False

    # TODO: Examine other versions of the file format and if this parser
    # supports them.
    stripped_line = line.rstrip()
    return stripped_line == '#Version: 1.5'


text_parser.SingleLineTextParser.RegisterPlugin(WinFirewallLogTextPlugin)
