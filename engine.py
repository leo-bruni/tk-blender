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

"""
A Blender engine for Tank (ShotGrid Toolkit).
https://www.blender.org/
"""

import os
import sys
import time
import atexit
import logging
import traceback

import tank
from tank.log import LogManager
from tank.platform import Engine
from tank.util import is_windows, is_linux, is_macos

import bpy
from bpy.app.handlers import persistent

# ---------------------------------------------------------------------
# NEW: Attempt direct PySide2 import, then fall back to PySide6
# ---------------------------------------------------------------------
try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"

ENGINE_NAME = "tk-blender"
ENGINE_NICE_NAME = "Shotgun Blender Engine"
APPLICATION_NAME = "Blender"

# env variable that control if to show the compatibility warning dialog
# when Blender software version is above the tested one.
SHOW_COMP_DLG = "SGTK_COMPATIBILITY_DIALOG_SHOWN"

# this is the absolute minimum Blender version for the engine to work.
MIN_COMPATIBILITY_VERSION = 2.8

logger = LogManager.get_logger(__name__)


def display_message(level, msg):
    t = time.asctime(time.localtime())
    print("%s | %s | %s | %s " % (t, level, ENGINE_NICE_NAME, msg))


def display_error(msg):
    display_message("Error", msg)


def display_warning(msg):
    display_message("Warning", msg)


def display_info(msg):
    display_message("Info", msg)


def display_debug(msg):
    if os.environ.get("TK_DEBUG") == "1":
        display_message("Debug", msg)


@persistent
def on_scene_event_callback(*args, **kwargs):
    """
    Callback that's run whenever a scene is saved or opened.
    """
    try:
        refresh_engine()
    except Exception as e:
        logger.exception("Could not refresh the engine; error: '%s'" % e)
        (exc_type, exc_value, exc_traceback) = sys.exc_info()

        message = ""
        message += (
            "Message: Shotgun encountered a problem changing the Engine's context.\n"
        )
        message += "Please contact support@shotgunsoftware.com\n\n"
        message += "Exception: %s - %s\n" % (exc_type, exc_value)
        message += "Traceback (most recent call last):\n"
        message += "\n".join(traceback.format_tb(exc_traceback))

        # If a QApplication is running, show a critical message box:
        if QtWidgets.QApplication.instance():
            QtWidgets.QMessageBox.critical(None, ENGINE_NICE_NAME, message)

        print(message)


def setup_app_handlers():
    """
    Set up Blender callbacks for scene load/save to refresh the engine.
    """
    teardown_app_handlers()
    bpy.app.handlers.load_post.append(on_scene_event_callback)
    bpy.app.handlers.save_post.append(on_scene_event_callback)
    atexit.register(teardown_app_handlers)


def teardown_app_handlers():
    """
    Remove the previously registered handlers (if present).
    """
    if on_scene_event_callback in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_scene_event_callback)

    if on_scene_event_callback in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_scene_event_callback)


def refresh_engine():
    """
    Refresh the current engine based on the current file path/context.
    """
    logger.debug("Refreshing the engine")

    engine = tank.platform.current_engine()
    if not engine:
        logger.debug("No currently initialized engine found; aborting refresh.")
        return

    scene_name = bpy.data.filepath
    if not scene_name or scene_name in ("", "Untitled.blend"):
        logger.debug("File not saved yet; aborting refresh.")
        return

    scene_name = os.path.abspath(scene_name)
    current_context = engine.context

    try:
        tk = tank.sgtk_from_path(scene_name)
        logger.debug("Extracted sgtk instance '%r' from path '%r'", tk, scene_name)
    except tank.TankError:
        # Could not detect context from path, fallback to the existing project context:
        message = (
            "Shotgun %s Engine could not detect the context\n"
            "from the active document. Menus will stay in the current "
            "context '%s'.\n" % (APPLICATION_NAME, current_context)
        )
        display_warning(message)
        return

    ctx = tk.context_from_path(scene_name, current_context)

    if not ctx:
        # fallback to the project context
        project_name = engine.context.project.get("name")
        ctx = tk.context_from_entity_dictionary(engine.context.project)
        logger.debug(
            "Could not extract a context from the path, reverting to project "
            "'%r' context '%r'",
            project_name,
            ctx,
        )

    if ctx != current_context:
        try:
            engine.change_context(ctx)
        except tank.TankError:
            message = (
                "Shotgun %s Engine could not change context\n"
                "to '%r'. Shotgun menu will be disabled.\n" % (APPLICATION_NAME, ctx)
            )
            display_warning(message)
            engine.create_shotgun_menu(disabled=True)


class BlenderEngine(Engine):
    """
    Shotgun Toolkit engine for Blender.
    """

    def __init__(self, *args, **kwargs):
        self._qt_app = None
        self._qt_app_main_window = None
        self._menu_generator = None
        Engine.__init__(self, *args, **kwargs)

    def show_message(self, msg, level="info"):
        """
        Displays a dialog with the message according to the severity level.
        """
        try:
            from PySide2 import QtCore, QtGui, QtWidgets
        except ImportError:
            from PySide6 import QtCore, QtGui, QtWidgets

        level_icon = {
            "info": QtWidgets.QMessageBox.Information,
            "error": QtWidgets.QMessageBox.Critical,
            "warning": QtWidgets.QMessageBox.Warning,
        }

        dlg = QtWidgets.QMessageBox()
        dlg.setIcon(level_icon.get(level, QtWidgets.QMessageBox.Information))
        dlg.setText(msg)
        dlg.setWindowTitle(ENGINE_NICE_NAME)
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        dlg.show()
        dlg.exec_()

    def show_error(self, msg):
        self.show_message(msg, level="error")

    def show_warning(self, msg):
        self.show_message(msg, level="warning")

    def show_info(self, msg):
        self.show_message(msg, level="info")

    @property
    def context_change_allowed(self):
        return True

    @property
    def host_info(self):
        """
        Returns a dictionary with info about the host application.
        """
        host_info = {"name": "Blender", "version": "unknown"}
        try:
            host_info["version"] = bpy.app.version_string
        except Exception:
            pass
        return host_info

    def pre_app_init(self):
        """
        Runs after engine is set up but before apps init.
        """
        self.logger.debug("Initializing engine... %s", self)

        self.tk_blender = self.import_module("tk_blender")
        self.init_qt_app()

        # In older PySide2 code, you might set QTextCodec to handle unicode from SG.
        # PySide6 removed QTextCodec. If you need it, wrap in a check:
        if hasattr(QtCore, "QTextCodec"):
            utf8 = QtCore.QTextCodec.codecForName("utf-8")
            QtCore.QTextCodec.setCodecForCStrings(utf8)
            self.logger.debug("Set utf-8 codec for widget text")

    def init_engine(self):
        """
        Initializes the Blender engine (checks OS, Blender version, etc.).
        """
        self.logger.debug("%s: Initializing...", self)

        # check if OS is supported
        if not any([is_windows(), is_linux(), is_macos()]):
            raise tank.TankError(
                "Unsupported platform! Only Mac, Linux, and Windows 64 are supported."
            )

        # check Blender version
        build_version = bpy.app.version
        app_ver = float(".".join(map(str, build_version[:2])))

        if app_ver < MIN_COMPATIBILITY_VERSION:
            msg = (
                f"Shotgun integration is not compatible with {APPLICATION_NAME} "
                f"versions older than {MIN_COMPATIBILITY_VERSION}"
            )
            self.show_error(msg)
            raise tank.TankError(msg)

        self._menu_name = "Shotgun"
        if self.get_setting("use_sgtk_as_menu_name", False):
            self._menu_name = "Sgtk"

        if self.get_setting("automatic_context_switch", True):
            setup_app_handlers()
            self.logger.debug("Registered open/save callbacks for automatic context.")

    def create_shotgun_menu(self, disabled=False):
        """
        Creates the main Shotgun menu in Blender.
        """
        if self.has_ui:
            self.logger.debug("Creating Shotgun menu...")
            tk_blender = self.import_module("tk_blender")
            self._menu_generator = tk_blender.MenuGenerator(self, self._menu_name)
            self._menu_generator.create_menu(disabled=disabled)
        return False

    def display_menu(self, pos=None):
        """
        Shows the engine Shotgun menu.
        """
        if self._menu_generator:
            self._menu_generator.show(pos)

    def init_qt_app(self):
        """
        Ensure the QApplication is initialized and create a main window.
        """
        # if there is an existing Qt app, reuse it
        self._qt_app = QtWidgets.QApplication.instance()
        if not self._qt_app:
            # Usually Blender engine sets up QApplication in a separate script/operator
            self._qt_app = QtWidgets.QApplication(sys.argv)

        # set a window icon if desired
        self._qt_app.setWindowIcon(QtGui.QIcon(self.icon_256))
        self._qt_app.setQuitOnLastWindowClosed(False)

        if self._qt_app_main_window is None:
            self.log_debug("Initializing main QApplication window...")

            self._qt_app_main_window = QtWidgets.QMainWindow()
            # On Windows, try to parent under Blender’s main window
            if is_windows():
                import ctypes

                hwnd = ctypes.windll.user32.GetActiveWindow()
                if hwnd:
                    # Some code to embed might go here if needed
                    pass

            self._qt_app_central_widget = QtWidgets.QWidget()
            self._qt_app_main_window.setCentralWidget(self._qt_app_central_widget)

        # set up the dark style
        self._initialize_dark_look_and_feel()

        # try to match Blender's font size
        text_size = 9
        if len(bpy.context.preferences.ui_styles) > 0:
            self.log_debug("Applying Blender UI style to QApplication...")
            text_size = bpy.context.preferences.ui_styles[0].widget.points - 2

        ui_scale = bpy.context.preferences.system.ui_scale
        text_size *= ui_scale
        self._qt_app.setStyleSheet(
            f""".QMenu {{ font-size: {text_size}pt; }}
                .QWidget {{ font-size: {text_size}pt; }}"""
        )

        self.logger.debug("QT Application: %s", self._qt_app_main_window)

    def post_app_init(self):
        """
        Called after all apps have initialized.
        """
        tank.platform.engine.set_current_engine(self)
        self.create_shotgun_menu()

        # close windows created by the engine on exit
        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.destroy_engine)

        # Run configured startup commands
        self._run_app_instance_commands()

    def post_context_change(self, old_context, new_context):
        """
        Runs after a context change. Rebuilds menus if needed.
        """
        if self.get_setting("automatic_context_switch", True):
            setup_app_handlers()
            if old_context != new_context:
                self.create_shotgun_menu()

            self.sgtk.execute_core_hook_method(
                tank.platform.constants.CONTEXT_CHANGE_HOOK,
                "post_context_change",
                previous_context=old_context,
                current_context=new_context,
            )

    def _run_app_instance_commands(self):
        """
        Runs app instance commands listed in 'run_at_startup' from the environment config.
        """
        app_instance_commands = {}
        for (cmd_name, value) in self.commands.items():
            app_instance = value["properties"].get("app")
            if app_instance:
                cmd_dict = app_instance_commands.setdefault(app_instance.instance_name, {})
                cmd_dict[cmd_name] = value["callback"]

        for app_setting_dict in self.get_setting("run_at_startup", []):
            app_instance_name = app_setting_dict["app_instance"]
            setting_cmd_name = app_setting_dict["name"]

            cmd_dict = app_instance_commands.get(app_instance_name)
            if cmd_dict is None:
                self.logger.warning(
                    "%s 'run_at_startup' requests app '%s' which is not installed.",
                    self.name,
                    app_instance_name,
                )
            else:
                if not setting_cmd_name:
                    # run all commands for that app
                    for (cmd_name, command_function) in cmd_dict.items():
                        self.logger.debug(
                            "%s startup: running app '%s' command '%s'.",
                            self.name,
                            app_instance_name,
                            cmd_name,
                        )
                        command_function()
                else:
                    command_function = cmd_dict.get(setting_cmd_name)
                    if command_function:
                        self.logger.debug(
                            "%s startup: running app '%s' command '%s'.",
                            self.name,
                            app_instance_name,
                            setting_cmd_name,
                        )
                        command_function()
                    else:
                        known_commands = ", ".join("'%s'" % name for name in cmd_dict)
                        self.logger.warning(
                            "%s 'run_at_startup' requests unknown command '%s' in app '%s'. "
                            "Known commands: %s",
                            self.name,
                            setting_cmd_name,
                            app_instance_name,
                            known_commands,
                        )

    def destroy_engine(self):
        """
        Closes windows created by the engine before exiting the application.
        """
        self.logger.debug("%s: Destroying...", self)
        self.close_windows()

    def _get_dialog_parent(self):
        """
        Get the QWidget parent for all dialogs created via show_dialog & show_modal.
        """
        return self._qt_app_main_window

    @property
    def has_ui(self):
        """
        Detect if Blender is running with a UI (not in batch mode).
        """
        return not bpy.app.background

    def _emit_log_message(self, handler, record):
        """
        Called by the engine to log messages.
        """
        if record.levelno < logging.INFO:
            formatter = logging.Formatter("Debug: Shotgun %(basename)s: %(message)s")
        else:
            formatter = logging.Formatter("Shotgun %(basename)s: %(message)s")

        msg = formatter.format(record)

        if record.levelno >= logging.ERROR:
            fct = display_error
        elif record.levelno >= logging.WARNING:
            fct = display_warning
        elif record.levelno >= logging.INFO:
            fct = display_info
        else:
            fct = display_debug

        self.async_execute_in_main_thread(fct, msg)

    def close_windows(self):
        """
        Closes any open dialogs created by the engine.
        """
        opened_dialog_list = self.created_qt_dialogs[:]
        for dialog in opened_dialog_list:
            dialog_window_title = dialog.windowTitle()
            try:
                self.logger.debug("Closing dialog %s.", dialog_window_title)
                dialog.close()
            except Exception as exception:
                traceback.print_exc()
                self.logger.error(
                    "Cannot close dialog %s: %s", dialog_window_title, exception
                )
