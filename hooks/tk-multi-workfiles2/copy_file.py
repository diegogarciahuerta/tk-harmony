# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import glob
import shutil
import datetime

import sgtk
from sgtk.util.filesystem import copy_folder

HookClass = sgtk.get_hook_baseclass()


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


def listdir(directory_path, pattern="*"):
    for dirpath, dirnames, filenames in os.walk(directory_path):
        for file_name in fnmatch.filter(filenames, pattern):
            yield os.path.join(dirpath, file_name)


class CopyFile(HookClass):
    """
    Hook called when a file needs to be copied
    DGH241018
    In this case it is the hook used to copy the harmony project
    from publish to workfiles or from a sandbox to another.
    This means that not only the file needs to be copied but the src folder too
    In order to preserve other data in the destination folder we copy it into
    a 'history' folder if there are any collisions.
    """

    def execute(self, source_path, target_path, **kwargs):
        """
        Main hook entry point

        :source_path:   String
                        Source file path to copy

        :target_path:   String
                        Target file path to copy to
        """
        app = self.parent
        app.log_debug("-" * 50)
        app.log_debug("CopyFile Hook...")
        app.log_debug("CopyFile Hook - source_path: %s" % source_path)
        app.log_debug("CopyFile Hook - target_path: %s" % target_path)

        engine = sgtk.platform.current_engine()
        tk = engine.sgtk
        dcc_app = engine.app

        app.log_debug("kwargs: %s" % kwargs)
        app.log_debug("-" * 50)

        source_dir = os.path.dirname(source_path)
        target_dir = os.path.dirname(target_path)

        app.log_debug("CopyFile Hook - source_dir: %s" % source_dir)
        app.log_debug("CopyFile Hook - target_dir: %s" % target_dir)

        # create the folder if it doesn't exist
        if os.path.isdir(target_dir):
            app.log_debug("CopyFile Hook - target_dir does exist")
            has_content = glob.glob(os.path.join(target_dir, "*.xstage"))
            app.log_debug("CopyFile Hook - xstage files: %s" % has_content)
            if has_content:
                now = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                history_dir = os.path.join(target_dir, "..", "history", now)
                if not os.path.isdir(history_dir):
                    old_umask = os.umask(0)
                    os.makedirs(history_dir, 0777)
                    os.umask(old_umask)
                shutil.move(target_dir, history_dir)
        
        # check again as the previous process could have deleted the folder
        if not os.path.isdir(target_dir):
            app.log_debug("CopyFile Hook - target_dir does not exist")
            old_umask = os.umask(0)
            os.makedirs(target_dir, 0777)
            os.umask(old_umask)
            
        # copy the file renamed to whatever is mean to be
        shutil.copy(source_path, target_path)
        # copy the rest of the folders except for the file we just copied.
        copy_folder(source_dir, target_dir, folder_permissions=0o775, skip_list=[source_path])
