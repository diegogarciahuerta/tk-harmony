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
import re
import sys
import shutil
import hashlib
import socket
import platform
import subprocess

import sgtk
from sgtk.platform.errors import TankEngineInitError
from sgtk.platform import SoftwareLauncher, SoftwareVersion, LaunchInformation


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


logger = sgtk.LogManager.get_logger(__name__)

DIR_PATH = os.path.dirname(os.path.realpath(__file__))


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def samefile(file1, file2):
    return md5(file1) == md5(file2)


# based on:
# https://stackoverflow.com/questions/38876945/copying-and-merging-directories-excluding-certain-extensions
def copytree_multi(src, dst, symlinks=False, ignore=None):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    if not os.path.isdir(dst):
        os.makedirs(dst)

    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)

        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree_multi(srcname, dstname, symlinks, ignore)
            else:
                if os.path.exists(dstname):
                    if not samefile(srcname, dstname):
                        os.unlink(dstname)
                        shutil.copy2(srcname, dstname)
                        logger.info("File copied: %s" % dstname)
                    else:
                        # same file, so ignore the copy
                        logger.info("Same file, skipping: %s" % dstname)
                        pass
                else:
                    shutil.copy2(srcname, dstname)
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        except shutil.Error as err:
            errors.extend(err.args[0])
    try:
        shutil.copystat(src, dst)
    except WindowsError:
        pass
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise shutil.Error(errors)


def scripts_path_for_exec(exec_path):
    version_output_regex = (
        "(?P<company>Toon Boom) (?P<product>\w+) (?P<edition>\w+)\r\n"
        "(?P=product) (?P=edition) \((?P=product) *(?P=edition)(.exe)*\) version (?P<version>\d*\.*\d*\.*\d*) build (?P<build>\d*) (?P<build_date>.*)"
    )
    exec_version = subprocess.check_output(
        [exec_path, "-v"], stderr=subprocess.STDOUT
    )

    scripts_path = None
    exec_info_match = re.match(version_output_regex, exec_version, re.MULTILINE)

    if exec_info_match:
        exec_info = exec_info_match.groupdict()
        exec_info["scripts_version"] = exec_info.get("version").replace(".", "")

        if platform.system() == "Windows":
            path_root = os.path.expandvars("%APPDATA%")
        elif platform.system() == "Linux":
            path_root = os.path.expandvars("~")
        elif platform.system() == "Darwin":
            path_root = os.path.expandvars("~/Library/Preferences")

        if path_root:
            scripts_path = os.path.join(
                path_root,
                "%(company)s Animation" % exec_info,
                "%(company)s %(product)s %(edition)s" % exec_info,
                "%(scripts_version)s-scripts" % exec_info,
            )
    return scripts_path


def ensure_scripts_up_to_date(engine_scripts_path, scripts_folder):
    logger.info("Updating scripts...: %s" % engine_scripts_path)
    logger.info("                     scripts_folder: %s" % scripts_folder)

    copytree_multi(engine_scripts_path, scripts_folder)

    return True


def get_free_port():
    # Ask the OS to allocate a port.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class HarmonyLauncher(SoftwareLauncher):
    """
    Handles launching Harmony executables. Automatically starts up
    a tk-harmony engine with the current context in the new session
    of Harmony.
    """

    # Named regex strings to insert into the executable template paths when
    # matching against supplied versions and products. Similar to the glob
    # strings, these allow us to alter the regex matching for any of the
    # variable components of the path in one place.

    # It seems that Harmony does not use any version number in the
    # installation folders, as if they do not support multiple versions of
    # the same software.
    COMPONENT_REGEX_LOOKUP = {
        "version": r"\d\d\.*\d*",
        "platform": r" \(x86\)",
        "editiondir": r"\w+",
        "edition": r"\w+",
    }

    # This dictionary defines a list of executable template strings for each
    # of the supported operating systems. The templates are used for both
    # globbing and regex matches by replacing the named format placeholders
    # with an appropriate glob or regex string.

    EXECUTABLE_TEMPLATES = {
        "Windows": [
            "C:\\Program Files{platform}\\Toon Boom Animation\\Toon Boom Harmony {version} {editiondir}\\win64\\bin\\Harmony{edition}.exe"
        ],
        "Linux": [
            "/usr/local/ToonBoomAnimation/harmony{editiondir}_{version}/lnx86_64/bin/Harmony{edition}",
            "/opt/ToonBoomAnimation/harmony{editiondir}_{version}/lnx86_64/bin/Harmony{edition}",
        ],
        "Darwin": [
            "/Applications/Toon Boom Harmony {version} {editiondir}/Harmony {edition}.app/Contents/MacOS/Harmony {edition}"
        ],
    }

    @property
    def minimum_supported_version(self):
        """
        The minimum software version that is supported by the launcher.
        """
        return "16.0"

    def prepare_launch(self, exec_path, args, file_to_open=None):
        """
        Prepares an environment to launch Harmony in that will automatically
        load Toolkit and the tk-harmony engine when Harmony starts.

        :param str exec_path: Path to Harmony executable to launch.
        :param str args: Command line arguments as strings.
        :param str file_to_open: (optional) Full path name of a file to open on
                                            launch.
        :returns: :class:`LaunchInformation` instance
        """
        required_env = {}

        resources_packages_path = os.path.join(
            self.disk_location, "resources", "packages"
        )

        startup_js_path = os.path.join(
            self.disk_location, "resources", "startup", "bootstrap.js"
        )

        # Run the engine's init.py file when Harmony starts up
        # TODO, maybe start engine here
        startup_path = os.path.join(
            self.disk_location, "startup", "bootstrap.py"
        )

        # Prepare the launch environment with variables required by the
        # classic bootstrap approach.
        self.logger.debug(
            "Preparing Harmony Launch via Toolkit Classic methodology ..."
        )

        required_env["SGTK_HARMONY_EXEC_PATH"] = exec_path.replace("\\", "/")

        required_env["SGTK_HARMONY_ENGINE_STARTUP"] = startup_path.replace(
            "\\", "/"
        )

        required_env[
            "SGTK_HARMONY_ENGINE_JS_STARTUP"
        ] = startup_js_path.replace("\\", "/")

        required_env["SGTK_HARMONY_ENGINE_PYTHON"] = sys.executable.replace(
            "\\", "/"
        )

        resources_path = os.path.join(DIR_PATH, "resources")
        required_env[
            "SGTK_HARMONY_ENGINE_RESOURCES_PATH"
        ] = resources_path.replace("\\", "/")

        newfile_template_path = os.path.join(
            resources_path, "templates", "newfile", "template.xstage"
        )
        required_env[
            "SGTK_HARMONY_NEWFILE_TEMPLATE"
        ] = newfile_template_path.replace("\\", "/")

        required_env[
            "SGTK_HARMONY_MODULE_PATH"
        ] = sgtk.get_sgtk_module_path().replace("\\", "/")

        required_env["SGTK_HARMONY_ENGINE_HOST"] = "127.0.0.1"
        required_env["SGTK_HARMONY_ENGINE_PORT"] = str(get_free_port())

        if file_to_open:
            # Add the file name to open to the launch environment
            required_env["SGTK_FILE_TO_OPEN"] = file_to_open

        required_env["SGTK_ENGINE"] = self.engine_name
        required_env["SGTK_CONTEXT"] = sgtk.context.serialize(self.context)

        # ensure scripts are up to date on the dccc side
        scripts_path = scripts_path_for_exec(exec_path)
        self.logger.debug("Searching for scripts here: %s" % scripts_path)

        if scripts_path is None:
            message = ("Could not find the scripts path for "
                       "executable: %s\n" % exec_path)
            raise TankEngineInitError(message)

        user_scripts_path = os.path.join(scripts_path, "packages")

        # create scripts folder if it does not exist already
        if not os.path.exists(user_scripts_path):
            os.makedirs(user_scripts_path)

        xtage = os.path.join(
            self.disk_location,
            "resources",
            "templates",
            "startup",
            "template.xstage",
        )
        required_env["SGTK_HARMONY_STARTUP_TEMPLATE"] = xtage.replace("\\", "/")

        args = " -debug"
        args += ' "' + xtage + '"'

        self.logger.debug("Launch info: %s" % args)

        ensure_scripts_up_to_date(resources_packages_path, user_scripts_path)

        return LaunchInformation(exec_path, args, required_env)

    def _icon_from_engine(self):
        """
        Use the default engine icon as harmony does not supply
        an icon in their software directory structure.

        :returns: Full path to application icon as a string or None.
        """

        # the engine icon
        engine_icon = os.path.join(self.disk_location, "icon_256.png")
        return engine_icon

    def scan_software(self):
        """
        Scan the filesystem for harmony executables.

        :return: A list of :class:`SoftwareVersion` objects.
        """
        self.logger.debug("Scanning for Harmony executables...")

        supported_sw_versions = []
        for sw_version in self._find_software():
            (supported, reason) = self._is_supported(sw_version)
            if supported:
                supported_sw_versions.append(sw_version)
            else:
                self.logger.debug(
                    "SoftwareVersion %s is not supported: %s"
                    % (sw_version, reason)
                )

        return supported_sw_versions

    def _find_software(self):
        """
        Find executables in the default install locations.
        """

        # all the executable templates for the current OS
        platform_os = platform.system()
        executable_templates = self.EXECUTABLE_TEMPLATES.get(platform_os, [])

        # all the discovered executables
        sw_versions = []

        for executable_template in executable_templates:

            self.logger.debug("Processing template %s.", executable_template)

            executable_matches = self._glob_and_match(
                executable_template, self.COMPONENT_REGEX_LOOKUP
            )

            # Extract all products from that executable.
            for (executable_path, key_dict) in executable_matches:

                # extract the matched keys form the key_dict (default to None
                # if not included)
                executable_version = key_dict.get("version", None)
                executable_edition = key_dict.get("edition", "")
                self.logger.debug(
                    "Software found: %s | %s.",
                    executable_version,
                    executable_template,
                )
                sw_versions.append(
                    SoftwareVersion(
                        executable_version,
                        "Harmony %s" % executable_edition,
                        executable_path,
                        self._icon_from_engine(),
                    )
                )

        return sw_versions
