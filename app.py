# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Mantra Output App for Houdini
"""

import sgtk


class MantraOutputNode(sgtk.platform.Application):
    def init_app(self):
        module = self.import_module("tk_houdini_mantranode")
        self.handler = module.ToolkitMantraNodeHandler(self)

    def convert_to_mantra_nodes(self):
        """
        Convert all Shotgun Mantra nodes found in the current Script to regular
        Mantra nodes.  Additional toolkit information will be stored in
        user data named 'tk_*'
        """
        self.handler.convert_sg_to_mantra_nodes()

    def convert_from_mantra_nodes(self):
        """
        Convert all regular Mantra nodes that have previously been converted
        from Shotgun Mantra nodes, back into Shotgun Mantra nodes.
        """
        self.handler.convert_mantra_to_sg_nodes()
