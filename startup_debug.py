# ----------------------------------------------------------------------------
# Copyright (c) 2020, Diego Garcia Huerta.
#
# Your use of this software as distributed in this GitHub repository, is
# governed by the Apache License 2.0
#
# Your use of the Shotgun Pipeline Toolkit is governed by the applicable
# license agreement between you and Autodesk / Shotgun.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

import os
import sys
import tempfile
import subprocess

import sgtk
from sgtk.platform import SoftwareLauncher, SoftwareVersion, LaunchInformation

################################################################################
# RUN STARTUP WITH macOS TERMINAL LOGGING                                      #
################################################################################

__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"

# We store the location of PySide2 or 6 module in the site-packages.path file.
# This is so the resources/scripts/startup/Shotgun_menu.py can fine this
# location when it loads the ShotGun menu within Blender. It needs to load
# the same module, from the same location. If you install PySide6 in the users
# site-packages folder, this seems to prevent ShotGun from launching.
for path in sys.path:
    if "site-packages" in path and any(os.path.isdir(os.path.join(path, pkg))
                                      for pkg in ("PySide2", "PySide6")):
        site_packages_path = path
        break

if site_packages_path:
    path_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "site-packages.path"
    )
    try:
        with open(path_file, "w") as file:
            file.write(site_packages_path)
    except Exception as e:
        print(f"Could not save site-packages.path: {e}")

class BlenderLauncher(SoftwareLauncher):
    """
    Handles launching Blender executables. Automatically starts up
    a tk-blender engine with the current context in the new session
    of Blender.
    """

    # Named regex strings to insert into the executable template paths when
    # matching against supplied versions and products. Similar to the glob
    # strings, these allow us to alter the regex matching for any of the
    # variable components of the path in one place
    COMPONENT_REGEX_LOOKUP = {"version": r"\d.\d+(.\d*)*"}

    # This dictionary defines a list of executable template strings for each
    # of the supported operating systems. The templates are used for both
    # globbing and regex matches by replacing the named format placeholders
    # with an appropriate glob or regex string.

    # Blender can be installed in different locations, since we cannot predict
    # where it will be located, we resort to letting the user define an
    # environment variable that points to the folder location where the
    # executable is located, that way we cover all cases. The disadvantage of
    # this is that we do not get a version number out of it.
    EXECUTABLE_TEMPLATES = {
        "darwin": [
            "$BLENDER_BIN_DIR/Blender {version}",
            "/Applications/Blender{version}.app/Contents/MacOS/Blender",
        ],
        "win32": [
            "$BLENDER_BIN_DIR/blender.exe",
            "$USERPROFILE/AppData/Roaming/Blender Foundation/Blender/{version}/blender.exe",
            "C:/Program Files/Blender Foundation/Blender {version}/blender.exe",
            "C:/Program Files/Blender Foundation/Blender/blender.exe",
        ],
        "linux2": ["$BLENDER_BIN_DIR/blender", "/usr/share/blender/blender"],
    }

    @property
    def minimum_supported_version(self):
        return "2.8"

    def prepare_launch(self, exec_path, args, file_to_open=None):
        """
        Prepares an environment to launch Blender in that will automatically
        load Toolkit and the tk-blender engine when Blender starts.

        :param str exec_path: Path to Blender executable to launch.
        :param str args: Command line arguments as strings.
        :param str file_to_open: (optional) Full path name of a file to open on
                                 launch.
        :returns: :class:`LaunchInformation` instance
        """
        required_env = {}

        # Example: standard environment-building from your existing code
        scripts_path = os.path.join(self.disk_location, "resources", "scripts")
        startup_path = os.path.join(scripts_path, "startup", "Shotgun_menu.py")
        args += "-P " + startup_path

        required_env["BLENDER_USER_SCRIPTS"] = scripts_path

        if not os.environ.get("PYSIDE2_PYTHONPATH"):
            pyside2_python_path = os.path.join(self.disk_location, "python", "ext")
            required_env["PYSIDE2_PYTHONPATH"] = pyside2_python_path

        required_env["SGTK_MODULE_PATH"] = sgtk.get_sgtk_module_path().replace("\\", "/")
        engine_startup_path = os.path.join(self.disk_location, "startup", "bootstrap.py")
        required_env["SGTK_BLENDER_ENGINE_STARTUP"] = engine_startup_path
        required_env["SGTK_BLENDER_ENGINE_PYTHON"] = sys.executable.replace("\\", "/")
        required_env["SGTK_ENGINE"] = self.engine_name
        required_env["SGTK_CONTEXT"] = sgtk.context.serialize(self.context)

        if file_to_open:
            required_env["SGTK_FILE_TO_OPEN"] = file_to_open

        # Build a small shell script that sets env vars, then calls Blender. This
        # is the bit which forces logging from Blender to appear in macOS terminal
        shell_script_lines = [
            "#!/bin/bash\n",
            "# Auto-generated script to launch Blender in a Terminal\n",
        ]
        # Export each environment variable
        for key, val in required_env.items():
            val_escaped = val.replace('"', '\\"')
            shell_script_lines.append(f'export {key}="{val_escaped}"\n')
        shell_script_lines.append(f'"{exec_path}" {args}\n')
        shell_script_lines.append('read -p "Press [Enter] to close this window..."\n')

        # Write this script to a temp file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, mode="w", prefix="blender_launch_", suffix=".sh")
        script_path = tmp_file.name
        tmp_file.writelines(shell_script_lines)
        tmp_file.close()

        # Make it executable
        os.chmod(script_path, 0o755)

        # Use AppleScript to open a new Terminal window that runs our script
        apple_script = f'''
            tell application "Terminal"
                activate
                do script "{script_path}"
            end tell
        '''
        # Launch the AppleScript (async).
        subprocess.Popen(["osascript", "-e", apple_script])

        # Return a "dummy" LaunchInformation
        return LaunchInformation(
            None, None, None
        )

    def _icon_from_engine(self):
        """
        Use the default engine icon as blender does not supply
        an icon in their software directory structure.

        :returns: Full path to application icon as a string or None.
        """

        # the engine icon
        engine_icon = os.path.join(self.disk_location, "icon_256.png")
        return engine_icon

    def scan_software(self):
        """
        Scan the filesystem for blender executables.

        :return: A list of :class:`SoftwareVersion` objects.
        """
        self.logger.debug("Scanning for Blender executables...")

        supported_sw_versions = []
        for sw_version in self._find_software():
            (supported, reason) = self._is_supported(sw_version)
            if supported:
                supported_sw_versions.append(sw_version)
            else:
                self.logger.debug(
                    "SoftwareVersion %s is not supported: %s" % (sw_version, reason)
                )

        return supported_sw_versions

    def _find_software(self):
        """
        Find executables in the default install locations.
        """

        # all the executable templates for the current OS
        executable_templates = self.EXECUTABLE_TEMPLATES.get(sys.platform, [])

        # all the discovered executables
        sw_versions = []

        # Here we account for extra arguments passed to the blender command line
        # this allows a bit of flexibility without having to fork the whole
        # engine just for this reason.
        # Unfortunately this cannot be put in the engine.yml as I would like
        # to because the engine class has not even been instantiated yet.
        extra_args = os.environ.get("SGTK_BLENDER_CMD_EXTRA_ARGS")

        for executable_template in executable_templates:
            executable_template = os.path.expanduser(executable_template)
            executable_template = os.path.expandvars(executable_template)

            self.logger.debug("Processing template %s", executable_template)

            executable_matches = self._glob_and_match(
                executable_template, self.COMPONENT_REGEX_LOOKUP
            )

            # Extract all products from that executable.
            for (executable_path, key_dict) in executable_matches:

                # extract the matched keys form the key_dict.
                # in the case of version we return something different than
                # an empty string because there are cases were the installation
                # directories do not include version number information.
                executable_version = key_dict.get("version", " ")

                args = []
                if extra_args:
                    args.append(extra_args)

                sw_versions.append(
                    SoftwareVersion(
                        executable_version,
                        "Blender",
                        executable_path,
                        icon=self._icon_from_engine(),
                        args=args,
                    )
                )

        return sw_versions
