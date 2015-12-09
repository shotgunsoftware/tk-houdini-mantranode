# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

# built-ins
import os
import sys

# houdini
import hou

# toolkit
import sgtk


class TkMantraNodeHandler(object):
    """Handle Tk Mantra node operations and callbacks."""

    ############################################################################
    # Class data

    # mostly a collection of strings that are reused throughout the handler.  

    HOU_MANTRA_NODE_TYPE = "ifd"
    """Houdini type for mantra node."""

    NODE_OUTPUT_PATH_PARM = "sgtk_vm_filename"

    TK_EXTRA_PLANE_COUNT_PARM = 'vm_numaux'
    """Parameter that stores the number of aov planes."""

    TK_EXTRA_PLANE_TEMPLATE_MAPPING = {
        'sgtk_vm_filename_plane#': 'output_extra_plane_template'
    }
    """Maps additional plane parameter names to output template names"""

    TK_EXTRA_PLANES_NAME = "sgtk_aov_name_%s"
    """Placeholder used to format extra plane names"""

    TK_INIT_PARM_NAME = "sgtk_initialized"
    """Parameter used to store whether a tk mantra node has been initialized."""

    TK_HIP_PATH_PARM_NAME = 'sgtk_hip_path'
    """Holds cached path to the hip file."""

    TK_MANTRA_NODE_TYPE = "sgtk_mantra"
    """The clase of node as defined in Houdini for the Mantra nodes."""

    TK_OUTPUT_PROFILE_PARM = "sgtk_output_profile" 
    """The name of the parameter that stores the current output profile."""

    TK_OUTPUT_PROFILE_NAME_KEY = "tk_output_profile_name"
    """The key in the user data that stores the output profile name."""

    TK_RENDER_TEMPLATE_MAPPING = {
        "sgtk_soho_diskfile": "output_ifd_template",
        "sgtk_vm_dcmfilename": "output_dcm_template",
        "sgtk_vm_filename": "output_render_template",
    }
    """Mapping between tk mantra parms and corresponding render templates."""

    TK_RESET_PARM_NAMES = [
        "soho_compression",
        "soho_mkpath",
        "vm_device",
        "vm_image_exr_compression",
        "vm_image_jpeg_quality",
        "vm_image_tiff_compression",
    ]
    """The default parameters to reset when the profile changes."""

    TK_DEFAULT_UPDATE_PARM_MAPPING = {     
        "sgtk_soho_diskfile": "soho_diskfile",
        "sgtk_vm_dcmfilename": "vm_dcmfilename",
        "sgtk_vm_picture": "vm_picture",
    }
    """Map tk parms to mantra node parms."""

    ############################################################################
    # Class methods

    @classmethod
    def convert_back_to_tk_mantra_nodes(cls, app):
        """Convert Mantra nodes back to Toolkit Mantra nodes.

        :param app: The calling Toolkit Application

        Note: only converts nodes that had previously been Toolkit Mantra
        nodes.

        """

        # get all instances of the built-in mantra nodes
        mantra_nodes = hou.nodeType(
            hou.ropNodeTypeCategory(), cls.HOU_MANTRA_NODE_TYPE).instances()

        if not mantra_nodes:
            app.log_debug("No Mantra Nodes found for conversion.")
            return
        
        # iterate over all the mantra nodes and attempt to convert them
        for mantra_node in mantra_nodes:

            # get the user data dictionary stored on the node
            user_dict = mantra_node.userDataDict()

            # get the output_profile from the dictionary
            tk_output_profile_name = user_dict.get(
                cls.TK_OUTPUT_PROFILE_NAME_KEY)

            if not tk_output_profile_name:
                app.log_warning(
                    "Mantra node '%s' does not have an output profile name. "
                    "Can't convert to Tk Mantra node. Continuing." %
                    (mantra_node.name(),)
                )
                continue

            # create new Shotgun Write node:
            tk_node_type = TkMantraNodeHandler.TK_MANTRA_NODE_TYPE
            tk_mantra_node = mantra_node.parent().createNode(tk_node_type)

            # find the index of the stored name on the new tk mantra node
            # and set that item in the menu.
            try:
                output_profile_parm = tk_mantra_node.parm(
                    TkMantraNodeHandler.TK_OUTPUT_PROFILE_PARM)
                output_profile_index = output_profile_parm.menuLabels().index(
                    tk_output_profile_name)
                output_profile_parm.set(output_profile_index)
            except ValueError:
                app.log_warning("No output profile found named: %s" % 
                    (tk_output_profile_name,))

            # copy over all parameter values except the output path 
            _copy_parm_values(mantra_node, tk_mantra_node, excludes=[])

            # explicitly copy AOV settings to the new tk mantra node
            plane_numbers = _get_extra_plane_numbers(mantra_node)
            for plane_number in plane_numbers:
                plane_parm_name = self.TK_EXTRA_PLANES_NAME % (plane_number,)
                aov_name = user_dict.get(plane_parm_name)
                tk_mantra_node.parm(plane_parm_name).set(aov_name)

            # copy the inputs and move the outputs
            _copy_inputs(mantra_node, tk_mantra_node)
            _move_outputs(mantra_node, tk_mantra_node)

            # make the new node the same color. the profile will set a color, 
            # but do this just in case the user changed the color manually
            # prior to the conversion.
            tk_mantra_node.setColor(mantra_node.color())

            # remember the name and position of the original mantra node
            mantra_node_name = mantra_node.name()
            mantra_node_pos = mantra_node.position()

            # destroy the original mantra node
            mantra_node.destroy()

            # name and reposition the new, regular mantra node to match the
            # original
            tk_mantra_node.setName(mantra_node_name)
            tk_mantra_node.setPosition(mantra_node_pos)

            app.log_debug("Converted: Mantra node '%s' to TK Mantra node."
                % (mantra_node_name,))


    @classmethod
    def convert_to_regular_mantra_nodes(cls, app):
        """Convert Toolkit Mantra nodes to regular Mantra nodes.

        :param app: The calling Toolkit Application

        """

        # get all instances of tk mantra nodes
        tk_node_type = TkMantraNodeHandler.TK_MANTRA_NODE_TYPE
        tk_mantra_nodes = hou.nodeType(
            hou.ropNodeTypeCategory(), tk_node_type).instances()

        if not tk_mantra_nodes:
            app.log_debug("No Toolkit Mantra Nodes found for conversion.")
            return

        for tk_mantra_node in tk_mantra_nodes:


            # create a new, regular Mantra node
            mantra_node = tk_mantra_node.parent().createNode(
                cls.HOU_MANTRA_NODE_TYPE)

            # copy across knob values
            exclude_parms = [parm for parm in tk_mantra_node.parms() 
                if parm.name().startswith("sgtk_")]
            _copy_parm_values(tk_mantra_node, mantra_node,
                excludes=exclude_parms)

            # store the mantra output profile name in the user data so that we
            # can retrieve it later.
            output_profile_parm = tk_mantra_node.parm(
                cls.TK_OUTPUT_PROFILE_PARM)
            tk_output_profile_name = \
                output_profile_parm.menuLabels()[output_profile_parm.eval()]
            mantra_node.setUserData(cls.TK_OUTPUT_PROFILE_NAME_KEY, 
                tk_output_profile_name)

            # store AOV info on the new node
            plane_numbers = _get_extra_plane_numbers(tk_mantra_node)
            for plane_number in plane_numbers:
                plane_parm_name = self.TK_EXTRA_PLANES_NAME % (plane_number,)
                mantra_node.setUserData(plane_parm_name,
                    tk_mantra_node.parm(plane_parm_name).eval())

            # copy the inputs and move the outputs
            _copy_inputs(tk_mantra_node, mantra_node)
            _move_outputs(tk_mantra_node, mantra_node)

            # make the new node the same color
            mantra_node.setColor(tk_mantra_node.color())

            # remember the name and position of the original tk mantra node
            tk_mantra_node_name = tk_mantra_node.name()
            tk_mantra_node_pos = tk_mantra_node.position()

            # destroy the original tk mantra node
            tk_mantra_node.destroy()

            # name and reposition the new, regular mantra node to match the
            # original
            mantra_node.setName(tk_mantra_node_name)
            mantra_node.setPosition(tk_mantra_node_pos)

            app.log_debug("Converted: Tk Mantra node '%s' to Mantra node."
                % (tk_mantra_node_name,))


    ############################################################################
    # Instance methods

    def __init__(self, app):
        """Initialize the handler.
        
        :params app: The application instance. 
        
        """

        # keep a reference to the app for easy access to templates, settings,
        # logging methods, tank, context, etc.
        self._app = app

        # get and cache the list of profiles defined in the settings
        self._output_profiles = {}
        for output_profile in self._app.get_setting("output_profiles", []):
            output_profile_name = output_profile["name"]

            if output_profile_name in self._output_profiles:
                self._app.log_warning(
                    "Found multiple output profiles named '%s' for the "
                    "Tk Mantra node! Only the first one will be available." %
                    (output_profile_name,)
                )
                continue

            self._output_profiles[output_profile_name] = output_profile
            self._app.log_debug("Caching mantra output profile: '%s'" % 
                (output_profile_name,))


    ############################################################################
    # methods and callbacks executed via the OTL

    def copy_path_to_clipboard(self):

        render_path = self._get_render_path(hou.pwd())

        # use Qt to copy the path to the clipboard:
        from sgtk.platform.qt import QtGui
        QtGui.QApplication.clipboard().setText(render_path)

        self._app.log_debug(
            "Copied render path to clipboard: %s" % (render_path,))

    # get labels for all tk-houdini-mantranode output profiles
    def get_output_profile_menu_labels(self):

        menu_labels = []
        for count, output_profile_name in enumerate(self._output_profiles):
            menu_labels.extend([count, output_profile_name])

        return menu_labels


    # returns a list of output path menu items for the current node
    def get_output_path_menu(self, node=None):

        if not None:
            node = hou.pwd()

        # is this the first time this has been created?
        is_first_run = (node.parm(self.TK_INIT_PARM_NAME).eval() == "True")
        if is_first_run:
            # set it to false for subsequent calls
            node.parm(is_first_run).set("False")

        # see if the hip file has changed
        hip_path_changed = (
            hou.hipFile.path() == node.parm(self.TK_HIP_PATH_PARM_NAME).eval())

        if is_first_run or hip_path_changed:
            # make sure node is in default state.
            self.reset_render_path(node)

            # cache current hip file path to compare against later
            node.parm(self.TK_HIP_PATH_PARM_NAME).set(hou.hipFile.path())

        # get path from hidden parameter which acts like a cache.
        path = node.parm(self.NODE_OUTPUT_PATH_PARM).unexpandedString()

        # Build the menu
        menu = ["sgtk", path,
                "ip", "mplay (interactive)",
                "md", "mplay (non-interactive)"]

        return menu


    # Reset the render path of the specified node.  This will force the render
    # path to be updated based on the current script path and configuraton
    def reset_render_path(self, node=None):

        if not node:
            node = hou.pwd()

        # Checks to see if the supplied node is being copied. Houdini renames
        # the node by prepending original0_ to the original node when copying.
        if node.name().startswith('original0'):
            return

        for (parm_name, template_name) in \
            self.TK_RENDER_TEMPLATE_MAPPING.items():
            self._compute_and_set(node, parm_name, template_name)

        # Extra Image Planes / AOVs
        plane_numbers = _get_extra_plane_numbers(node)
        for plane_number in plane_numbers:
            for (parm_name, template_name) in \
                self.TK_EXTRA_PLANE_TEMPLATE_MAPPING.items():
                parm_name = parm_name.replace('#', str(plane_number))
                aov_name = node.parm(
                    self.TK_EXTRA_PLANES_NAME % (plane_number,)).eval()
                self._compute_and_set(node, parm_name, template_name, aov_name)

        # set the output paths
        path = node.parm(self.NODE_OUTPUT_PATH_PARM).unexpandedString()
        node.parm('sgtk_vm_picture').set(path)
        node.parm('vm_picture').set(path)

        self.update_parms(node)


    # apply the selected profile in the session
    def set_profile(self, node=None, reset=False):

        if not node:
            node = hou.pwd()

        output_profile = self._get_output_profile(node)

        self._app.log_debug("Applying tk mantra node profile: %s" % 
            (output_profile["name"],))

        # reset some parameters if need be
        if reset:
            for parm_name in self.TK_RESET_PARM_NAMES:
                parm = node.parm(parm_name)
                if parm:
                    parm.revertToDefaults()

            node.setColor(hou.Color([.8, .8, .8]))

        # apply the supplied settings to the node
        settings = output_profile["settings"]
        if settings:
            self._app.log_debug('Populating format settings: %s' % 
                (file_settings,))
            node.setParms(settings)

        # set the node color
        color = output_profile["color"]
        if color:
            node.setColor(hou.Color(color))

        self.reset_render_path(node)


    # open a file browser showing the render path of the current node
    def show_in_fs(self):

        # retrieve the calling node
        current_node = hou.pwd()
        if not current_node:
            return

        render_dir = None

        # first, try to just use the current cached path:
        render_path = self._get_render_path(current_node)

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
            rendered_files = self._get_rendered_files(current_node)

            if not rendered_files:
                msg = ("Unable to find rendered files for node '%s'." 
                       % (current_node,))
                self._app.log_error(msg)
                hou.ui.displayMessage(msg)
                return
            else:
                render_dir = os.path.dirname(rendered_files[0])

        # if we have a valid render path then show it:
        if render_dir:
            # TODO: move to utility method in core
            system = sys.platform

            # run the app
            if system == "linux2":
                cmd = "xdg-open \"%s\"" % render_dir
            elif system == "darwin":
                cmd = "open '%s'" % render_dir
            elif system == "win32":
                cmd = "cmd.exe /C start \"Folder\" \"%s\"" % render_dir
            else:
                msg = "Platform '%s' is not supported." % (system,)
                self._app.log_error(msg)
                hou.ui.displayMessage(msg)

            self._app.log_debug("Executing command:\n '%s'" % (cmd,))
            exit_code = os.system(cmd)
            if exit_code != 0:
                msg = "Failed to launch '%s'!" % (cmd,)
                hou.ui.displayMessage(msg)

    # called when the node is created
    def setup_node(self, node):
        
        default_name = self._app.get_setting('default_node_name')
        node.setName(default_name, unique_name=True)

        # apply the default profile
        self.set_profile(node, reset=True)

        # make sure the render paths are in default state
        self.reset_render_path(node)


    def update_parms(self, node=None):

        if not node:
            node = hou.pwd()

        # copies the value of one parm to another
        copy_parm = lambda p1, p2: \
            node.parm(p2).set(node.parm(p1).unexpandedString())

        # copy the default udpate parms
        for parm1, parm2 in self.TK_DEFAULT_UPDATE_PARM_MAPPING.items():
            copy_parm(parm1, parm2)

        # handle additional planes
        plane_numbers = _get_extra_plane_numbers(node)
        for plane_number in plane_numbers:
            for parm1, parm2 in \
                self.TK_EXTRA_PLANE_TEMPLATE_MAPPING.items():
                parm1 = parm1.replace('#', str(num))
                parm2 = parm2.replace('#', str(num))
                copy_parm(parm1, parm2)

    
    # Callback for "Different File" checkbox on every Extra Image Plane.  Sets
    # the AOV Name to Channel Name or VEX Variable.  Resets the render paths to
    # update the path for this AOV.  Sets the Label to "Disabled." when it is
    # unchecked.
    def use_file_plane(self, node, parm):

        # replace the parm basename with nothing, leaving the plane number
        plane_number = parm.name().replace('vm_usefile_plane', '')

        if parm.eval():

            value = node.parm("vm_channel_plane%s" % (num,)).eval()
            if not value:
                value = node.parm("vm_variable_plane%s" % (num,)).eval()
            node.parm(self.TK_EXTRA_PLANES_NAME % (num,)).set(value)
            self.reset_render_path(node)
        else:
            path_parm = node.parm("sgtk_vm_filename_plane%s" % (num,))
            path_parm.lock(False)
            path_parm.set('Disabled')
            path_parm.lock(True)
            path_node.parm(self.TK_EXTRA_PLANES_NAME % (num,)).set("")


    ############################################################################
    # Private methods

    # compute and set and output path for the supplied parm
    def _compute_and_set(self, node, parm_name, template_name, aov_name=None):

        try:
            path = self._compute_output_path(node, template_name, aov_name)
        except sgtk.TankError as err:
            self._app.log_warning("%s: %s" % (node.name(), err))
            path = "ERROR: %s" % (err,)

        # Unlock, set, lock
        node.parm(parm_name).lock(False)
        node.parm(parm_name).set(path)
        node.parm(parm_name).lock(True)


    # compute the output path based on the current work file and render template
    def _compute_output_path(self, node, template_name, aov_name=None):

        # Get relevant fields from the scene filename and contents
        work_file_fields = self._get_hipfile_fields()

        if not work_file_fields:
            msg = "This Houdini file is not a Shotgun Toolkit work file!"
            raise sgtk.TankError(msg)

        output_profile = self._get_output_profile(node)

        # Get the render template from the app
        output_template = self._app.get_template_by_name(
            output_profile[template_name])

        # create fields dict with all the metadata
        fields = {
            "name": work_file_fields.get("name", None),
            "node": node.name(),
            "renderpass": node.name(),
            "SEQ": "FORMAT: $F",
            "version": work_file_fields.get("version", None),
        } 

        # use %V - full view printout as default for the eye field
        fields["eye"] = "%V"

        if aov_name:
            fields["aov_name"] = aov_name

        # Get the camera width and height if necessary
        if "width" in output_template.keys or "height" in output_template.keys:
            width, height = _get_render_resolution(node)
            fields["width"] = width
            fields["height"] = height

        fields.update(self._app.context.as_template_fields(output_template))

        path = output_template.apply_fields(fields)
        path = path.replace(os.path.sep, '/')

        return path


    # get the current output profile
    def _get_output_profile(self, node=None):

        if not node:
            node = hou.pwd()

        output_profile_parm = node.parm(self.TK_OUTPUT_PROFILE_PARM)
        output_profile_name = \
            output_profile_parm.menuLabels()[output_profile_parm.eval()]
        return self._output_profiles[output_profile_name]


    # extract fields from current Houdini file using the workfile template
    def _get_hipfile_fields(self):
        current_file_path = hou.hipFile.path()

        work_fields = {}
        work_file_template = self._app.get_template("work_file_template")
        if (work_file_template and 
            work_file_template.validate(current_file_path)):
            work_fields = work_file_template.get_fields(current_file_path)

        return work_fields


    # get the render path from current item in the output path parm menu
    def _get_render_path(self, node):
        output_parm = node.parm(self.NODE_OUTPUT_PATH_PARM)
        return output_parm.unexpandedString()

    
    # returns the files on disk associated with this node
    def _get_rendered_files(self, node):

        file_name = self._get_render_path(node)
        output_profile = self._get_output_profile(node)

        # get the output cache template for the current profile
        output_render_template = self._app.get_template_by_name(
            output_profile["output_render_template"])

        if not output_render_template.validate(file_name):
            msg = ("Unable to validate files on disk for node %s."
                   "The path '%s' is not recognized by Shotgun."
                   % (node.name(), file_name))
            self._app.log_error(msg)
            return []
            
        fields = output_render_template.get_fields(file_name)

        # get the actual file paths based on the template. Ignore any sequence
        # or eye fields
        return self._app.tank.paths_from_template(
            output_render_template, fields, ["SEQ", "eye"])


################################################################################
# Utility methods

# Copy all the input connections from this node to the target node.
def _copy_inputs(source_node, target_node):

    input_connections = source_node.inputConnections()
    num_target_inputs = len(target_node.inputConnectors())

    if len(input_connections) > num_target_inputs:
        raise hou.InvalidInput(
            "Not enough inputs on target node. Cannot copy inputs from "
            "'%s' to '%s'" % (source_node, target_node)
        )
        
    for connection in input_connections:
        target_node.setInput(connection.inputIndex(),
            connection.inputNode())


# Copy parameter values of the source node to those of the target node if a
# parameter with the same name exists.
def _copy_parm_values(source_node, target_node, excludes=None):

    if not excludes:
        excludes = []

    # build a parameter list from the source node, ignoring the excludes
    source_parms = [
        parm for parm in source_node.parms() if parm.name() not in excludes]

    for source_parm in source_parms:

        source_parm_template = source_parm.parmTemplate()

        # skip folder parms
        if isinstance(source_parm_template, hou.FolderSetParmTemplate):
            continue

        target_parm = target_node.parm(source_parm.name())

        # if the parm on the target node doesn't exist, skip it
        if target_parm is None:
            continue

        # if we have keys/expressions we need to copy them all.
        if source_parm.keyframes():
            for key in source_parm.keyframes():
                target_parm.setKeyframe(key)
        else:
            # if the parameter is a string, copy the raw string.
            if isinstance(source_parm_template, hou.StringParmTemplate):
                target_parm.set(source_parm.unexpandedString())
            # copy the evaluated value
            else:
                target_parm.set(source_parm.eval())


# return a list of aov plane nubmers
def _get_extra_plane_numbers(node):
    return xrange(1,
        node.parm(TkMantraNodeHandler.TK_EXTRA_PLANE_COUNT_PARM).eval() + 1)


# get the render resolution for the supplied node based on its camera parm
def _get_render_resolution(node):

    # Get the camera
    cam_path = node.parm("camera").eval()
    cam_node = hou.node(cam_path)

    if not cam_node:
        raise sgtk.TankError("Camera %s not found." % (cam_path,))

    width = cam_node.parm("resx").eval()
    height = cam_node.parm("resy").eval()

    # Calculate Resolution Override
    if node.parm('override_camerares').eval():
        scale = node.parm('res_fraction').eval()
        if scale == 'specific':
            width = node.parm('res_overridex').eval()
            height = node.parm('res_overridey').eval()
        else:
            width = int(float(width) * float(scale))
            height = int(float(height) * float(scale))

    return width, height


# move all the output connections from the source node to the target node
def _move_outputs(source_node, target_node):

    for connection in source_node.outputConnections():
        output_node = connection.outputNode()
        output_node.setInput(connection.inputIndex(), target_node)


