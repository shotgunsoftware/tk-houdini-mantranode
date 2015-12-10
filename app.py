# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Mantra Output node App for use with Toolkit's Houdini engine.
"""

import sgtk


class TkMantraNodeApp(sgtk.platform.Application):
    """The Mantra Output Node."""

    def init_app(self):
        """Initialize the app."""

        tk_houdini_mantra = self.import_module("tk_houdini_mantranode")
        self.handler = tk_houdini_mantra.TkMantraNodeHandler(self)

    def convert_to_regular_mantra_nodes(self):
        """Convert Toolkit Mantra nodes to regular Mantra nodes.

        Convert all Tooklit Mantra nodes found in the current script to 
        regular Mantra nodes. Additional Toolkit information will be stored in
        user data named 'tk_*'

        Example usage::

        >>> import sgtk
        >>> eng = sgtk.platform.current_engine()
        >>> app = eng.apps["tk-houdini-mantranode"]
        >>> app.convert_to_regular_mantra_nodes()

        """

        self.log_debug(
            "Converting Toolkit Mantra nodes to built-in Mantra nodes.")
        tk_houdini_mantra = self.import_module("tk_houdini_mantranode")
        tk_houdini_mantra.TkMantraNodeHandler.\
            convert_to_regular_mantra_nodes(self)

    def convert_back_to_tk_mantra_nodes(self):
        """Convert regular Mantra nodes back to Toolkit Mantra nodes.

        Convert any regular Mantra nodes that were previously converted
        from Toolkit Mantra nodes back into Toolkit Mantra nodes.

        Example usage::

        >>> import sgtk
        >>> eng = sgtk.platform.current_engine()
        >>> app = eng.apps["tk-houdini-mantranode"]
        >>> app.convert_back_to_tk_mantra_nodes()

        """

        self.log_debug(
            "Converting built-in Mantra nodes back to Toolkit Mantra nodes.")
        tk_houdini_mantra = self.import_module("tk_houdini_mantranode")
        tk_houdini_mantra.TkMantraNodeHandler.\
            convert_back_to_tk_mantra_nodes(self)


