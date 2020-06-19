"""
Module that encapsulates access to the actual application

"""


import os
import glob
import traceback
from itertools import chain

from .client import QTcpSocketClient
from .utils import copy_tree, normpath, Cached


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


class Application(QTcpSocketClient):
    def __init__(self, engine, parent=None, host=None, port=None):
        super(Application, self).__init__(parent=parent, host=host, port=port)
        self.engine = engine
        self.engine.logger.debug("Started Application: %s" % self)

    def connect(self):
        while not self.is_connected():
            self.connect_to_host()
            self.engine.logger.debug("Waiting for server: %s" % self.connection_status())

    def broadcast_event(self, event_name):
        self.send_command(event_name)

    def log_info(self, message):
        self.send_command("LOG_INFO", message=message)

    def log_warning(self, message):
        self.send_command("LOG_WARNING", message=message)

    def log_debug(self, message):
        self.send_command("LOG_DEBUG", message=message)

    def log_error(self, message):
        self.send_command("LOG_ERROR", message=message)

    def log_exception(self, message):
        self.send_command("LOG_EXCEPTION", message=message)

    def toggle_debug_logging(self, enabled):
        self.send_command("TOGGLE_DEBUG_LOGGING", enabled=enabled)

    def get_application_version(self):
        version = self.send_and_receive_command("GET_VERSION")
        self._app_version = str(version)
        return self._app_version

    get_application_version = Cached(get_application_version)

    def get_current_project_path(self):
        current_path = self.send_and_receive_command("GET_CURRENT_PROJECT_PATH")
        if current_path:
            current_path = normpath(str(current_path))
        else:
            current_path = "Unknown"

        return current_path

    def open_project(self, path):
        path = normpath(path)
        current_path = self.send_and_receive_command("OPEN_PROJECT", path=path)
        if current_path:
            current_path = normpath(str(current_path))

        return current_path

    def save_project(self):
        current_path = self.send_and_receive_command("SAVE_PROJECT")
        if current_path:
            current_path = normpath(str(current_path))

        return current_path

    def needs_saving(self, path):
        result = self.send_and_receive_command("NEEDS_SAVING", path=path)
        return result

    def save_new_version(self, version_name):
        current_path = self.send_and_receive_command(
            "SAVE_NEW_VERSION", version_name=version_name
        )
        if current_path:
            current_path = normpath(str(current_path))

        return current_path

    def is_startup_project(self):
        result = self.send_and_receive_command("IS_STARTUP_PROJECT")
        return result

    def execute(self, statement_str):
        result = self.send_and_receive_command("EXECUTE_STATEMENT", statement=statement_str)
        return result

    def extract_thumbnail(self, filename):
        result = self.send_and_receive_command("EXTRACT_THUMBNAIL", path=filename)
        return result

    # file management
    def new_file(self, app, context):
        import sgtk.platform

        # In Harmony we cannot really have a non saved project, so we
        # have to create one from scratch given a template to follow.
        app.log_debug("Copying the template project")

        # Suggest to save the project if it's modified
        app.log_debug("Checking if needing to save...")
        current_path = self.get_current_project_path()

        needs_saving = self.needs_saving(current_path)
        app.log_debug("Needs saving: %s" % needs_saving)

        app_settings = sgtk.platform.find_app_settings(
            app.engine.name, app.name, app.sgtk, context, app.engine.instance_name
        )

        settings = None
        for app_setting in app_settings:
            if app_setting.get("app_instance") == app.instance_name:
                settings = app_setting.get("settings")
                break

        if not settings:
            raise TankError(
                "Could not find the settings for app: %s context: %s" % (app.name, context)
            )

        # check if we have a different template to copy from than the original
        template_project_folder = settings.get("template_project_folder", None)
        if template_project_folder and os.path.exists(template_project_folder):
            source_path = template_project_folder
        else:
            source_path = os.environ["SGTK_HARMONY_NEWFILE_TEMPLATE"]

        # now we copy the newfile template to the destination path
        app.log_debug("Source_path: %s" % source_path)

        work_template = app.get_template_from(settings, "template_work")

        fields = {}

        ext_is_used = "extension" in work_template.keys
        name_is_used = "name" in work_template.keys
        version_is_used = "version" in work_template.keys

        if name_is_used:
            fields["name"] = "scene"
        if ext_is_used:
            fields["extension"] = "xstage"

        ctx_fields = context.as_template_fields(work_template, validate=True)
        fields = dict(chain(fields.iteritems(), ctx_fields.iteritems()))

        destination_path = None
        # very cheap way to get the next available version
        if version_is_used:
            version = 1
            while True:
                fields["version"] = version
                destination_path = work_template.apply_fields(fields)
                if not os.path.exists(destination_path):
                    break
                version += 1

        # Harmony saves projects in folders
        destination_folder, destination_filename = os.path.split(destination_path)
        destination_folder = normpath(destination_folder).replace("\\", "/")
        app.log_debug("Destination_folder: %s" % destination_folder)
        app.log_debug("Destination_filename: %s" % destination_filename)

        source_path_dir, source_path_filename = os.path.split(source_path)
        copy_tree(
            source_path_dir,
            destination_folder,
            rename_files={source_path_filename: destination_filename},
        )

        # and open it
        destination_path = normpath(destination_path).replace("\\", "/")
        app.log_debug("Opening new project: %s" % destination_path)
        self.open_project(destination_path)

        return True

    def save_new_version_action(self):
        result = self.send_and_receive_command("SAVE_NEW_VERSION_ACTION")
        return result

    def _copy_tree(self, *args, **kwargs):
        """
        We expose this function here for the hooks to take advantage of it
        """
        copy_tree(*args, **kwargs)

    def save_project_as(self, target_file, source_file=None, open_project=True):
        self.engine.logger.debug("Saving project as...")

        if source_file is None:
            source_file = self.get_current_project_path()

        source_folder, source_filename = os.path.split(source_file)
        source_filename_file, source_filename_ext = os.path.splitext(source_filename)

        target_folder, target_filename = os.path.split(target_file)
        target_filename_file, target_filename_ext = os.path.splitext(target_filename)

        # we need to ignore all the other versions within the
        # folder of this WIP version except for the ones that
        # we are publishing.
        include_files = [source_filename, source_filename_file + ".aux"]

        # start ingoring them all, but them add the good ones back
        exclude_patterns = ["*.xstage", "*.aux", "*.*~"]

        exclude_files = []
        for exclude_pattern in exclude_patterns:
            exclude_pattern_path = os.path.join(source_folder, exclude_pattern)
            exclude_files.extend(glob.glob(exclude_pattern_path))

        # just get the filenames names from their path
        exclude_files = map(os.path.basename, exclude_files)

        # make sure we keep the good ones!
        exclude_files = filter(lambda x: x not in include_files, exclude_files)

        # rename the files from source folder to publish folder
        rename_files = {}
        if source_filename != target_filename:
            rename_files[source_filename] = target_filename

        if source_filename_file + ".aux" != target_filename_file + ".aux":
            rename_files[source_filename_file + ".aux"] = target_filename_file + ".aux"

        # copy the folder to target
        # Note that I would happily use shutil.copytree, but we need to rename
        # files as they go from source to publish folder.
        # Also at the time of writting, shutil.copytree does not provide
        # the fancy callbacks that other python versions allow to choose your
        # own copy function, which could have become handy to inject the
        # renaming functionality.
        try:
            target_parent_folder = os.path.dirname(target_folder)
            if not os.path.exists(target_parent_folder):
                os.makedirs(target_parent_folder)

            self._copy_tree(
                source_folder,
                target_folder,
                exclude_files=exclude_files,
                rename_files=rename_files,
            )

        except Exception as e:
            raise Exception(
                "Failed to copy source folder from '%s' to '%s'.\n%s"
                % (source_folder, target_folder, traceback.format_exc())
            )

        self.engine.logger.debug(
            "Copied source folder '%s' to folder '%s'." % (source_folder, target_folder)
        )

        if open_project:
            self.open_project(target_file)

    # timeline
    def get_start_frame(self):
        result = self.send_and_receive_command("GET_START_FRAME")
        return result

    def set_start_frame(self, start_frame):
        result = self.send_and_receive_command("SET_START_FRAME", start_frame=start_frame)
        return result

    def get_stop_frame(self):
        result = self.send_and_receive_command("GET_STOP_FRAME")
        return result

    def set_stop_frame(self, stop_frame):
        result = self.send_and_receive_command("SET_STOP_FRAME", stop_frame=stop_frame)
        return result

    def get_frame_range(self):
        result = self.send_and_receive_command("GET_FRAME_RANGE")
        return result

    def set_frame_range(self, start_frame, stop_frame):
        result = self.send_and_receive_command(
            "SET_FRAME_RANGE", start_frame=start_frame, stop_frame=stop_frame
        )
        return result

    def get_frame_count(self):
        result = self.send_and_receive_command("GET_FRAME_COUNT")
        return result

    def set_frame_count(self, frame_count):
        result = self.send_and_receive_command("SET_FRAME_COUNT", frame_count=frame_count)
        return result

    # scene editing / management
    def import_project_resource(self, path, action):
        result = None

        # make sure we have a Harmony friendly path
        path = path.replace("\\", "/")

        if action == "drawing":
            result = self.send_command("IMPORT_DRAWING", path=path)

        if action == "3d":
            result = self.send_command("IMPORT_DRAWING", path=path)

        if action == "sound":
            result = self.send_command("IMPORT_AUDIO", path=path)

        if action == "movie":
            result = self.send_command("IMPORT_CLIP", path=path)

        return result

    def get_nodes_of_type(self, node_types):
        result = self.send_and_receive_command("GET_NODES_OF_TYPE", node_types=node_types)
        return result

    def get_node_metadata(self, node, attr_name):
        result = self.send_and_receive_command(
            "GET_NODE_METADATA", node=node, attr_name=attr_name
        )
        return result

    def get_scene_metadata(self, attr_name):
        result = self.send_and_receive_command("GET_SCENE_METADATA", attr_name=attr_name)
        return result

    def get_columns_of_type(self, column_type):
        result = self.send_and_receive_command("GET_COLUMNS_OF_TYPE", column_type=column_type)
        return result

    def get_sound_column_filenames(self, column_name):
        result = self.send_and_receive_command(
            "GET_SOUND_COLUMN_FILENAMES", column_name=column_name
        )
        return result
