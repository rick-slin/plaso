#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2013 The Plaso Project Authors.
# Please see the AUTHORS file for details on individual authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This file contains the Property List (Plist) Parser.

Plaso's engine calls PlistParser when it encounters Plist files to be processed.
"""

import binascii
import logging

from binplist import binplist

from plaso.lib import errors
from plaso.lib import utils
from plaso.parsers import interface
from plaso.parsers import manager


class PlistParser(interface.BasePluginsParser):
  """De-serializes and parses plists the event objects are generated by plist.

  The Plaso engine calls parsers by their Parse() method. This parser's
  Parse() has GetTopLevel() which deserializes plist files using the binplist
  library and calls plugins (PlistPlugin) registered through the
  interface by their Process() to produce event objects.

  Plugins are how this parser understands the content inside a plist file,
  each plugin holds logic specific to a particular plist file. See the
  interface and plist_plugins/ directory for examples of how plist plugins are
  implemented.
  """

  NAME = 'plist'
  DESCRIPTION = u'Parser for binary and text plist files.'

  _plugin_classes = {}

  def __init__(self):
    """Initializes a parser object."""
    super(PlistParser, self).__init__()
    self._plugins = PlistParser.GetPluginObjects()

  def GetTopLevel(self, file_object, file_name=''):
    """Returns the deserialized content of a plist as a dictionary object.

    Args:
      file_object: A file-like object to parse.
      file_name: The name of the file-like object.

    Returns:
      A dictionary object representing the contents of the plist.
    """
    try:
      top_level_object = binplist.readPlist(file_object)
    except binplist.FormatError as exception:
      raise errors.UnableToParseFile(
          u'[{0:s}] File is not a plist file: {1:s}'.format(
              self.NAME, utils.GetUnicodeString(exception)))
    except (
        LookupError, binascii.Error, ValueError, AttributeError) as exception:
      raise errors.UnableToParseFile(
          u'[{0:s}] Unable to parse XML file, reason: {1:s}'.format(
              self.NAME, exception))
    except OverflowError as exception:
      raise errors.UnableToParseFile(
          u'[{0:s}] Unable to parse: {1:s} with error: {2:s}'.format(
              self.NAME, file_name, exception))

    if not top_level_object:
      raise errors.UnableToParseFile(
          u'[{0:s}] File is not a plist: {1:s}'.format(
              self.NAME, utils.GetUnicodeString(file_name)))

    # Since we are using readPlist from binplist now instead of manually
    # opening up the BinarPlist file we loose this option. Keep it commented
    # out for now but this needs to be tested a bit more.
    # TODO: Re-evaluate if we can delete this or still require it.
    #if bpl.is_corrupt:
    #  logging.warning(
    #      u'[{0:s}] corruption detected in binary plist: {1:s}'.format(
    #          self.NAME, file_name))

    return top_level_object

  def Parse(self, parser_context, file_entry):
    """Parse and extract values from a plist file.

    Args:
      parser_context: A parser context object (instance of ParserContext).
      file_entry: A file entry object (instance of dfvfs.FileEntry).
    """
    # TODO: Should we rather query the stats object to get the size here?
    file_object = file_entry.GetFileObject()
    file_size = file_object.get_size()

    if file_size <= 0:
      file_object.close()
      raise errors.UnableToParseFile(
          u'[{0:s}] file size: {1:d} bytes is less equal 0.'.format(
              self.NAME, file_size))

    # 50MB is 10x larger than any plist seen to date.
    if file_size > 50000000:
      file_object.close()
      raise errors.UnableToParseFile(
          u'[{0:s}] file size: {1:d} bytes is larger than 50 MB.'.format(
              self.NAME, file_size))

    top_level_object = None
    try:
      top_level_object = self.GetTopLevel(file_object, file_entry.name)
    except errors.UnableToParseFile:
      file_object.close()
      raise

    if not top_level_object:
      file_object.close()
      raise errors.UnableToParseFile(
          u'[{0:s}] unable to parse: {1:s} skipping.'.format(
              self.NAME, file_entry.name))

    file_system = file_entry.GetFileSystem()
    plist_name = file_system.BasenamePath(file_entry.name)

    for plugin_object in self._plugins:
      try:
        event_object_generator = plugin_object.Process(
            parser_context, plist_name=plist_name, top_level=top_level_object)

        # TODO: remove this once the yield-based parsers have been replaced
        # by produce (or emit)-based variants.
        for event_object in event_object_generator:
          parser_context.ProduceEvent(
              event_object, parser_name=self.NAME,
              plugin_name=plugin_object.NAME, file_entry=file_entry)

      except errors.WrongPlistPlugin as exception:
        logging.debug(u'[{0:s}] Wrong plugin: {1:s} for: {2:s}'.format(
            self.NAME, exception[0], exception[1]))

    file_object.close()


manager.ParsersManager.RegisterParser(PlistParser)
