# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

# IMPORT STANDARD MODULES
import os
import sys

# IMPORT THIRD PARTY MODULES
import hou
import sgtk


class ToolkitMantraNodeHandler(object):

    SG_NODE_CLASS = "sgtk_mantra"
    PARM_CONFIG = 'sgtk__config'

    def __init__(self, app):
        self._app = app
        self._script_template = self._app.get_template("template_script_work")

        # cache the profiles:
        self._profile_names = []
        self._profiles = {}
        for profile in self._app.get_setting("mantra_nodes", []):
            name = profile["name"]
            if name in self._profiles:
                msg = """Configuration contains multiple Mantra Node profiles
                called '%s'!  Only the first will be available""" % name
                self._app.log_warning(msg)
                continue

            self._profile_names.append(name)
            self._profiles[name] = profile

    ############################################################################
    # Properties

    @property
    def profile_names(self):
        """
        Return the list of available profile names.

        :returns: Available profile names.
        :rtype: List
        """
        return self._profile_names

    ############################################################################
    # Public methods

    @staticmethod
    def get_nodes():
        """
        Returns a list of all SGTK Mantra nodes.

        :returns: All SGTK Mantra nodes.
        :rtype: List
        """
        node_class = ToolkitMantraNodeHandler.SG_NODE_CLASS
        rop_nodes = hou.nodeType(hou.ropNodeTypeCategory(),
                                 node_class).instances()
        return rop_nodes

    @staticmethod
    def get_node_name(node):
        """
        Return the name for the specified node.

        :arg node: Node to return name of
        :type node: hou.Node
        :returns: Name of node.
        :rtype: String
        """
        return node.name()

    @staticmethod
    def get_node_profile_name(node):
        """
        Return the name of the profile the specified node is using.

        :arg node: Node to return selected profile name of
        :type node: hou.Node
        :returns: Name of profile.
        :rtype: String
        """
        config_parm = node.parm(ToolkitMantraNodeHandler.PARM_CONFIG)
        return config_parm.menuLabels()[config_parm.eval()]

    def get_render_template(self, node):
        """
        Returns the associated render template obj for a node.

        :arg node: Node to return selected profile name of
        :type node: hou.Node
        :returns: Render template.
        :rtype: SGTK Template
        """
        return self.__get_template(node, "template_render")

    def get_files_on_disk(self, node):
        """
        Called from render publisher & UI (via exists_on_disk)
        Returns the files on disk associated with this node

        :arg node: Node to return files for.
        :type node: hou.Node
        :returns: Path.
        :rtype: String
        """
        return self.__get_files_on_disk(node)

    def reset_render_path(self, node):
        """
        Reset the render path of the specified node.  This
        will force the render path to be updated based on
        the current script path and configuraton

        :arg node: Node to reset render paths.
        :type node: hou.Node
        """
        self.__update_render_path(node)
        self.__set_initial_output_picture(node)
        self.__update_parms(node)

    def convert_sg_to_mantra_nodes(self):
        """
        Utility function to convert all Shotgun Write nodes to regular
        Mantra nodes.

        # Example use:
        import sgtk
        eng = sgtk.platform.current_engine()
        app = eng.apps["tk-houdini-mantranode"]
        # Convert Shotgun write nodes to Mantra nodes:
        app.convert_to_mantra_nodes()
        """

        # get write nodes:
        sg_nodes = self.get_nodes()
        for sg_n in sg_nodes:

            node_name = sg_n.name()
            node_pos = sg_n.position()

            # create new regular Write node:
            new_n = sg_n.parent().createNode("ifd")

            # copy across any knob values from the internal write node.
            # parmTuples
            exclude = [f for f in sg_n.parms() if f.name().startswith('sgtk__')]
            self.__copy_parm_values(sg_n, new_n, exclude)

            # Store Toolkit specific information on write node
            # so that we can reverse this process later

            # Profile Name
            new_n.setUserData('tk_profile_name',
                              self.get_node_profile_name(sg_n))

            # AOV Names
            nums = self.__get_all_extra_plane_numbers(sg_n)
            for num in nums:
                parm_name = 'sgtk__aov_name{0}'.format(num)
                user_data_name = 'tk_aov_name{0}'.format(num)
                new_n.setUserData(user_data_name,
                                  sg_n.parm(parm_name).eval())

            # Copy inputs and move outputs
            self.__copy_inputs_to_node(sg_n, new_n)
            self.__move_outputs_to_node(sg_n, new_n)
            self.__copy_color(sg_n, new_n)

            # delete original node:
            sg_n.destroy()

            # rename new node:
            new_n.setName(node_name)
            new_n.setPosition(node_pos)

    def convert_mantra_to_sg_nodes(self):
        """
        Utility function to convert all Mantra nodes to Shotgun
        Mantra nodes (only converts Mantra nodes that were previously
        Shotgun Mantra nodes)

        # Example use:
        import sgtk
        eng = sgtk.platform.current_engine()
        app = eng.apps["tk-houdini-mantranode"]
        # Convert previously converted Mantra nodes back to
        # Shotgun Mantra nodes:
        app.convert_from_write_nodes()
        """

        # get write nodes:
        nodes = hou.nodeType(hou.ropNodeTypeCategory(), 'ifd').instances()
        for n in nodes:

            user_dict = n.userDataDict()

            profile = user_dict.get('tk_profile_name')

            if not profile:
                # can't convert to a Shotgun Mantra Node
                # as we have missing parameters!
                continue

            node_name = n.name()
            node_pos = n.position()

            # create new Shotgun Write node:
            node_class = ToolkitMantraNodeHandler.SG_NODE_CLASS
            new_sg_n = n.parent().createNode(node_class)

            # set the profile
            try:
                parm = new_sg_n.parm(ToolkitMantraNodeHandler.PARM_CONFIG)
                index = parm.menuLabels().index(profile)
                parm.set(index)
            except ValueError:
                pass

            # copy across and knob values from the internal write node.
            exclude = []
            self.__copy_parm_values(n, new_sg_n, exclude)

            # explicitly copy some settings to the new Shotgun Mantra Node:
            # AOV Names
            nums = self.__get_all_extra_plane_numbers(n)
            for num in nums:
                parm_name = 'sgtk__aov_name{0}'.format(num)
                user_data_name = 'tk_aov_name{0}'.format(num)
                aov_name = user_dict.get(user_data_name)
                new_sg_n.parm(parm_name).set(aov_name)

            # Copy inputs and move outputs
            self.__copy_inputs_to_node(n, new_sg_n)
            self.__move_outputs_to_node(n, new_sg_n)
            self.__copy_color(n, new_sg_n)

            # delete original node:
            n.destroy()

            # rename new node:
            new_sg_n.setName(node_name)
            new_sg_n.setPosition(node_pos)

    ############################################################################
    # Public methods called from OTL - although these are public, they should
    # be considered as private and not used directly!
    def on_create_output_picture_menu(self, node):
        """
        Creates the output path menu.
        Used by parms: sgtk__vm_picture (menu script)

        :arg node: Node this is running on.
        :type node: hou.Node
        :returns: Menu list with token, label tuple.
        :rtype: List
        """
        if self.__is_first_run(node) or self.__has_hip_path_changed():
            self.reset_render_path(node)
            self.__save_hip_path_to_user_data()

        # Get path from hidden parameter which acts like a cache.
        key = 'sgtk__vm_filename'
        path = node.parm(key).unexpandedString()

        # Build the menu
        menu = [path, 'sgtk',
                'ip', 'mplay (interactive)',
                'md', 'mplay (non-interactive)']

        return menu

    def on_output_picture_render_method_callback(self, node):
        """
        Callback for when the menu on the "Output Picture" was changed.
        E.g. from SGTK Path to mplay (interactive)
        Will update all paramater on the node for the normal Houdini parameter
        to represent the sgtk__ counterparts.
        Used by parms: sgtk__vm_picture

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        self.__update_parms(node)

    def on_create_configuration_menu(self):
        """
        Script function to return the "Configuration" menu items/labels.
        Used by parms: sgtk__config (menu script)

        :returns: Menu list with token, label tuple.
        :rtype: List
        """
        return self.__get_configuration_menu_labels()

    def on_configuration_menu_callback(self, node):
        """
        Callback when "Configuration" menu was changed. Will call __set_profile
        to update everything for the new profile.
        Used by parms: sgtk__config

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        new_profile_name = self.get_node_profile_name(node)
        self.__set_profile(node, new_profile_name, reset_all_settings=True)

    def on_created_callback(self, node):
        """
        Callback when node was created. Will set the default_node_name.
        Sets the default profile (first in the list).
        Resets the render paths.
        Used by scripts: OnCreated

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        self.__set_default_node_name(node)
        new_profile_name = self.get_node_profile_name(node)
        self.__set_profile(node, new_profile_name, reset_all_settings=True)
        self.reset_render_path(node)

    def on_usefile_plane_callback(self, node, parm):
        """
        Callback for "Different File" checkbox on every Extra Image Plane.
        Sets the AOV Name to Channel Name or VEX Variable.
        Resets the render paths to update the path for this AOV.
        Sets the Label to "Disabled." when it is unchecked.
        Used by parms: vm_usefile_plane#

        :arg node: Node this is running on.
        :type node: hou.Node
        :arg parm: Parm this is running on.
        :type parm: hou.Parm
        """
        num = parm.name().replace('vm_usefile_plane', '')

        if parm.eval():
            channel_name = node.parm('vm_channel_plane' + num).eval()
            vex_name = node.parm('vm_variable_plane' + num).eval()
            name = channel_name if channel_name else vex_name
            node.parm('sgtk__aov_name' + num).set(name)
            self.reset_render_path(node)
        else:
            parm = node.parm('sgtk__vm_filename_plane' + num)
            parm.lock(False)
            parm.set('Disabled')
            parm.lock(True)
            node.parm('sgtk__aov_name' + num).set('')

    def on_aov_name_changed_callback(self, node):
        """
        Callback for when the AOV Name was changed. Will reset the render paths
        to stay up to date.
        Used by parms: sgtk__aov_name#

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        self.reset_render_path(node)

    def on_resolution_changed_callback(self, node):
        """
        Callback for when the resolution override changes.
        Used by parms: override_camerares, res_fraction, res_override

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        self.reset_render_path(node)

    def on_name_changed_callback(self, node):
        """
        Callback when node was renamed. Checks if this is a copy action to
        prevent false errors.
        Used by scripts: OnNameChanged

        :arg node: Node this is running on.
        :type node: hou.Node
        """
        if not self.__is_node_being_copied(node):
            self.reset_render_path(node)

    def on_copy_path_to_clipboard_button_callback(self):
        """
        Callback from the node whenever the 'Copy path to clipboard' button
        is pressed.
        Used by parms: sgtk__copypath_button
        """
        node = hou.pwd()

        # get the path depending if in full or proxy mode:
        render_path = self.__get_render_path(node)

        # use Qt to copy the path to the clipboard:
        from sgtk.platform.qt import QtGui
        QtGui.QApplication.clipboard().setText(render_path)

    def on_show_in_fs_button_callback(self):
        """
        Shows the location of the node in the file system.
        This is a callback which is executed when the show in fs
        button is pressed on the node.
        Used by parms: sgtk__showinfs_button
        """
        node = hou.pwd()
        if not node:
            return

        render_dir = None

        # first, try to just use the current cached path:
        render_path = self.__get_render_path(node)
        if render_path:
            # the above method returns houdini style slashes, so ensure these
            # are pointing correctly
            render_path = render_path.replace("/", os.path.sep)

            dir_name = os.path.dirname(render_path)
            if os.path.exists(dir_name):
                render_dir = dir_name

        if not render_dir:
            # render directory doesn't exist so try using location
            # of rendered frames instead:
            try:
                files = self.get_files_on_disk(node)
                if len(files) == 0:
                    msg = ("There are no renders for this node yet!\n"
                           "When you render, the files will be written to "
                           "the following location:\n\n%s" % render_path)
                    hou.ui.displayMessage(msg)
                else:
                    render_dir = os.path.dirname(files[0])
            except Exception, e:
                msg = ("Unable to jump to file system:\n\n%s" % e)
                hou.ui.displayMessage(msg)

        # if we have a valid render path then show it:
        if render_dir:
            system = sys.platform

            # run the app
            if system == "linux2":
                cmd = "xdg-open \"%s\"" % render_dir
            elif system == "darwin":
                cmd = "open '%s'" % render_dir
            elif system == "win32":
                cmd = "cmd.exe /C start \"Folder\" \"%s\"" % render_dir
            else:
                raise Exception("Platform '%s' is not supported." % system)

            self._app.log_debug("Executing command '%s'" % cmd)
            exit_code = os.system(cmd)
            if exit_code != 0:
                msg = ("Failed to launch '%s'!" % cmd)
                hou.ui.displayMessage(msg)

    ############################################################################
    # Private methods

    @staticmethod
    def __is_node_being_copied(node):
        """
        Checks if the node is being copied right now by checking the name.
        Houdini is renaming the node by prepending original0_ to the original
        node.

        :arg node: Node this is running on.
        :type node: hou.Node
        :returns: True if node is being copied, False if not.
        :rtype: Boolean
        """
        return True if node.name().startswith('original0') else False

    def __set_profile(self, node, profile_name, reset_all_settings=False):

        # get the profile details:
        profile = self._profiles.get(profile_name)
        file_settings = profile["settings"]

        # set the format
        self.__populate_format_settings(node, file_settings, reset_all_settings)

        # Set tile color
        tile_color = profile.get("tile_color")
        if tile_color:
            self.__set_tile_color(node, tile_color)
        elif reset_all_settings:
            self.__reset_tile_color(node)

    @staticmethod
    def __set_tile_color(node, tile_color):
        color = hou.Color(tile_color)
        node.setColor(color)

    @staticmethod
    def __reset_tile_color(node):
        default_color = [0.8, 0.8, 0.8]
        color = hou.Color(default_color)
        node.setColor(color)

    @staticmethod
    def __copy_color(node_a, node_b):
        color_a = node_a.color()
        node_b.setColor(color_a)

    @staticmethod
    def __reset_parms(node, parm_names=None):
        # If parm_names is not provided use the following output specific list.
        # Output specific parms. Try not to reset parms related to anything
        # else.
        format_specific = ['vm_device',
                           'soho_mkpath',
                           'vm_image_jpeg_quality',
                           'vm_image_tiff_compression',
                           'vm_image_exr_compression',
                           'soho_compression']
        parm_names = parm_names if parm_names else format_specific
        for parm_name in parm_names:
            parm = node.parm(parm_name)
            parm.revertToDefaults()

    def __populate_format_settings(self, node, file_settings,
                                   reset_all_settings=False):
        """
        Controls the file format of the write node

        :param node:                The Shotgun Write node to set the profile on
        :param file_type:           The file type to set on the internal Write
                                    node
        :param file_settings:       A dictionary of settings to set on the
                                    internal Write node
        :param reset_all_settings:  Determines if all settings should be set on
                                    the internal Write node (True) or just those
                                    that aren't propagated to the Shotgun Write
                                    node (False)
        """
        if reset_all_settings:
            self.__reset_parms(node)

        # now apply file format settings
        self._app.log_debug('Populating format settings: {0}'.format(
            file_settings))
        node.setParms(file_settings)

    @staticmethod
    def __set_initial_output_picture(node):
        path = node.parm('sgtk__vm_filename').unexpandedString()
        node.parm('sgtk__vm_picture').set(path)
        node.parm('vm_picture').set(path)

    def __get_node_profile_settings(self, node):
        """
        Find the profile settings for the specified node
        """
        profile_name = self.get_node_profile_name(node)
        if profile_name:
            return self._profiles.get(profile_name)
        else:
            return None

    def __has_hip_path_changed(self):
        current = hou.hipFile.path()
        cached = self.__load_hip_path_from_user_data()
        return current != cached

    @staticmethod
    def __is_first_run(node):
        key = 'sgtk__initialized'
        is_first_run = node.parm(key).eval()
        if not is_first_run == 'True':
            node.parm(key).set('True')
        else:
            is_first_run = False
        return is_first_run

    @staticmethod
    def __save_hip_path_to_user_data(path=None, node=None):
        path = path if path else hou.hipFile.path()
        node = node if node else hou.pwd()
        node.parm('sgtk__hip_path').set(path)

    @staticmethod
    def __load_hip_path_from_user_data(node=None):
        node = node if node else hou.pwd()
        return node.parm('sgtk__hip_path').eval()

    @staticmethod
    def __copy_inputs_to_node(node, target, ignore_missing=False):
        """ Copy all the input connections from this node to the
            target node.

            ignore_missing: If the target node does not have enough
                            inputs then skip this connection.
        """
        input_connections = node.inputConnections()

        num_target_inputs = len(target.inputConnectors())
        if num_target_inputs is 0:
            raise hou.OperationFailed("Target node has no inputs.")

        for connection in input_connections:
            index = connection.inputIndex()
            if index > (num_target_inputs - 1):
                if ignore_missing:
                    continue
                else:
                    raise hou.InvalidInput("Target node has too few inputs.")

            target.setInput(index, connection.inputNode())

    @staticmethod
    def __move_outputs_to_node(node, target):
        """ Move all the output connections from this node to the
            target node.
        """
        output_connections = node.outputConnections()

        for connection in output_connections:
            node = connection.outputNode()
            node.setInput(connection.inputIndex(), target)

    @staticmethod
    def __copy_parm_values(source_node, target_node, exclude=None):
        """
        Copy parameter values of the source node to those of the target node
        if a parameter with the same name exists.
        """
        exclude = exclude if exclude else []
        parms = [p for p in source_node.parms() if p.name() not in exclude]
        for parm_to_copy in parms:

            parm_template = parm_to_copy.parmTemplate()
            # Skip folder parms.
            if isinstance(parm_template, hou.FolderSetParmTemplate):
                continue

            parm_to_copy_to = target_node.parm(parm_to_copy.name())
            # If the parm on the target node does not exist, skip this parm.
            if parm_to_copy_to is None:
                continue

            # If we have keys/expressions we need to copy them all.
            if parm_to_copy.keyframes():
                # Copy all hou.Keyframe objects.
                for key in parm_to_copy.keyframes():
                    parm_to_copy_to.setKeyframe(key)
            else:
                # If the parameter is a string copy the raw string.
                if isinstance(parm_template, hou.StringParmTemplate):
                    parm_to_copy_to.set(parm_to_copy.unexpandedString())
                # Copy the raw value.
                else:
                    parm_to_copy_to.set(parm_to_copy.eval())

    def __get_hipfile_fields(self):
        """
        Extract fields from the current Houdini file using the template
        """
        curr_filename = hou.hipFile.path()

        work_fields = {}
        if self._script_template \
                and self._script_template.validate(curr_filename):
            work_fields = self._script_template.get_fields(curr_filename)

        return work_fields

    @staticmethod
    def __get_render_path(node):
        output_parm = node.parm('sgtk__vm_filename')
        path = output_parm.unexpandedString()
        return path

    def __get_template(self, node, name):
        """
        Get the named template for the specified node.
        """
        template_name = None

        # get the template from the nodes profile settings:
        settings = self.__get_node_profile_settings(node)
        if settings:
            template_name = settings[name]

        return self._app.get_template_by_name(template_name)

    def __get_files_on_disk(self, node):
        """
        Called from render publisher & UI (via exists_on_disk)
        Returns the files on disk associated with this node
        """
        file_name = self.__get_render_path(node)
        template = self.__get_template(node, "template_render")

        if not template.validate(file_name):
            msg = ("Could not resolve the files on disk for node %s."
                   "The path '%s' is not recognized by Shotgun!"
                   % (node.name(), file_name))
            raise Exception(msg)

        fields = template.get_fields(file_name)

        # make sure we don't look for any eye - %V or SEQ - %04d stuff
        frames = self._app.tank.paths_from_template(template, fields,
                                                    ["SEQ", "eye"])
        return frames

    def __update_parms(self, node):

        def copy_path_to_parm(key_, value_):
            path_ = node.parm(key_).unexpandedString()
            node.parm(value_).set(path_)

        map_ = {'sgtk__vm_picture': 'vm_picture',
                'sgtk__soho_diskfile': 'soho_diskfile',
                'sgtk__vm_dcmfilename': 'vm_dcmfilename'}
        for key, value in map_.items():
            copy_path_to_parm(key, value)

        # Extra Image Planes / AOVs
        extra = {'sgtk__vm_filename_plane#': 'vm_filename_plane#'}
        nums = self.__get_all_extra_plane_numbers(node)
        for num in nums:
            for key, value in extra.items():
                key = key.replace('#', str(num))
                value = value.replace('#', str(num))
                copy_path_to_parm(key, value)

    @staticmethod
    def __get_all_extra_plane_numbers(node):
            numbers = xrange(1, node.parm('vm_numaux').eval() + 1)
            return numbers

    def __gather_render_resolution(self, node):
        # Get the camera
        cam_path = node.parm("camera").eval()
        cam_node = hou.node(cam_path)
        if not cam_node:
            raise sgtk.TankError("Camera %s not found." % cam_path)
        width = cam_node.parm("resx").eval()
        height = cam_node.parm("resy").eval()

        # Calculate Resolution Override
        if self.__has_res_override(node):
            scale = node.parm('res_fraction').eval()
            if scale == 'specific':
                width = node.parm('res_overridex').eval()
                height = node.parm('res_overridey').eval()
            else:
                width = int(float(width) * float(scale))
                height = int(float(height) * float(scale))

        return width, height

    @staticmethod
    def __has_res_override(node):
        return node.parm('override_camerares').eval()

    def __compute_path(self, node, settings, template_alias, aov_name=None):
        # Get relevant fields from the scene filename and contents
        work_file_fields = self.__get_hipfile_fields()
        if not work_file_fields:
            msg = "This Houdini file is not a Shotgun Toolkit work file!"
            raise sgtk.TankError(msg)

        # Get the templates from the node settings
        template_name = settings.get(template_alias)
        template = self._app.get_template_by_name(template_name)

        if not template:
            msg = 'No Template provided for "{0}"'
            raise sgtk.TankError(msg.format(template_name))

        # create fields dict with all the metadata
        fields = dict()
        fields["name"] = work_file_fields.get("name")
        fields["version"] = work_file_fields["version"]
        # fields["node"] = self.get_node_name(node)
        fields["renderpass"] = self.get_node_name(node)
        fields["SEQ"] = "FORMAT: $F"

        if aov_name:
            # fields["channel"] = channel_name
            fields["aov_name"] = aov_name

        # Get the camera width and height if necessary
        if "width" in template.keys or "height" in template.keys:
            width, height = self.__gather_render_resolution(node)
            fields["width"] = width
            fields["height"] = height

        fields.update(self._app.context.as_template_fields(template))

        path = template.apply_fields(fields)
        path = path.replace('\\', '/')
        return path

    def __update_render_path(self, node):
        """
        Update the render path and the various feedback knobs based on the
        current context and other node settings.

        :param node:        The Shotgun Write node to update the path for
        :param force_reset: Force the path to be reset regardless of any cached
                            values
        :param is_proxy:    If True then update the proxy render path, otherwise
                            just update the normal render path.
        :returns:           The updated render path
        """
        def compute_and_set(node_, parm_name, node_settings_,
                            value_, aov_name_=None):
            try:
                path = self.__compute_path(node_, node_settings_, value_,
                                           aov_name_)
            except sgtk.TankError as err:
                warn_err = '{0}: {1}'.format(node_.name(), err)
                self._app.log_warning(warn_err)
                path = "ERROR: {0}".format(err)
            # Unlock parm
            node_.parm(parm_name).lock(False)
            # Set path
            node_.parm(parm_name).set(path)
            # Lock parm
            node_.parm(parm_name).lock(True)

        node_settings = self.__get_node_profile_settings(node)

        map_ = {'sgtk__vm_filename': 'template_render',
                'sgtk__soho_diskfile': 'template_ifd',
                'sgtk__vm_dcmfilename': 'template_dcm'}
        for key, value in map_.items():
            compute_and_set(node, key, node_settings, value)

        # Extra Image Planes / AOVs
        extra = {'sgtk__vm_filename_plane#': 'template_extra_plane'}
        nums = self.__get_all_extra_plane_numbers(node)
        for num in nums:
            for key, value in extra.items():
                key = key.replace('#', str(num))
                aov_name = node.parm('sgtk__aov_name{0}'.format(num)).eval()
                compute_and_set(node, key, node_settings, value, aov_name)

    def __get_configuration_menu_labels(self):
        # Combine two lists in alternating fashion.
        menu_labels = [None] * (2 * len(self._profile_names))
        menu_labels[::2] = ['sgtk'] * len(self._profile_names)
        menu_labels[1::2] = self._profile_names
        return menu_labels

    def __set_default_node_name(self, node):
        node_settings = self.__get_node_profile_settings(node)
        name = node_settings.get('default_node_name')
        if name:
            node.setName(name, unique_name=True)
