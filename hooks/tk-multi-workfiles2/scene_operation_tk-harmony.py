# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import shutil
import subprocess

import sgtk
from sgtk.platform.qt import QtGui
from sgtk.errors import TankError

HookClass = sgtk.get_hook_baseclass()


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


class SceneOperation(HookClass):
    """
    Hook called to perform an operation with the
    current scene
    """

    pre_save_context = None

    def execute(
        self,
        operation,
        file_path,
        context,
        parent_action,
        file_version,
        read_only,
        **kwargs
    ):
        """
        Main hook entry point

        :param operation:       String
                                Scene operation to perform

        :param file_path:       String
                                File path to use if the operation
                                requires it (e.g. open)

        :param context:         Context
                                The context the file operation is being
                                performed in.

        :param parent_action:   This is the action that this scene operation is
                                being executed for.  This can be one of:
                                - open_file
                                - new_file
                                - save_file_as
                                - version_up

        :param file_version:    The version/revision of the file to be opened.  If this is 'None'
                                then the latest version should be opened.

        :param read_only:       Specifies if the file should be opened read-only or not

        :returns:               Depends on operation:
                                'current_path' - Return the current scene
                                                 file path as a String
                                'reset'        - True if scene was reset to an empty
                                                 state, otherwise False
                                all others     - None
        """
        app = self.parent
        engine = sgtk.platform.current_engine()
        tk = engine.sgtk
        dcc_app = engine.app

        app.log_debug("-" * 50)
        app.log_debug("operation: %s" % operation)
        app.log_debug("file_path: %s" % file_path)
        app.log_debug("context: %s" % context)
        app.log_debug("app context: %s" % app.context)
        app.log_debug("engine context: %s" % engine.context)
        app.log_debug("parent_action: %s" % parent_action)
        app.log_debug(
            "SceneOperation.pre_save_context: %s"
            % SceneOperation.pre_save_context
        )
        app.log_debug("file_version: %s" % file_version)
        app.log_debug("read_only: %s" % read_only)
        app.log_debug("kwargs: %s" % kwargs)
        app.log_debug("-" * 50)

        prev_save_context = context
        if operation == "current_path":
            # Note this is a little bit of a trick for when the artist saves
            # into a different context.
            # Hamorny WIP file versions are all kept in the same
            # folder, so when a context is changes, we need to
            # actually copy the whole project to a different location.
            # This is a way to know the context has changed, as the action
            # at the time "save_as" operation is called does not provide
            # this information
            if parent_action == "save_file_as":
                SceneOperation.pre_save_context = context
            return dcc_app.get_current_project_path()

        elif operation == "open":
            dcc_app.open_project(file_path)
            return True

        elif operation == "save":
            dcc_app.save_project()

        elif operation == "save_as":
            app.log_debug("saving as " + file_path)
            if context == SceneOperation.pre_save_context:
                _, file_path_filename = os.path.split(file_path)
                version_name, _ = os.path.splitext(file_path_filename)
                dcc_app.save_new_version(version_name)
            else:
                # need to copy the project into a different location
                app.log_debug("saving as in a different context!")
                source_file = dcc_app.get_current_project_path()
                app.log_debug("source_file: %s" % source_file)
                app.log_debug("target_file: %s" % file_path)
                dcc_app.save_project_as(
                    file_path, source_file=source_file, open_project=True
                )

        elif operation == "reset":
            if parent_action not in ("new_file", "open_file"):
                dcc_app.close_project()
            return True

        elif operation == "prepare_new":
            return dcc_app.new_file(app, context)
