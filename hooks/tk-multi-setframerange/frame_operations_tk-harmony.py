# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


__author__ = "Diego Garcia Huerta"
__contact__ = "https://www.linkedin.com/in/diegogh/"


class FrameOperation(HookBaseClass):
    """
    Hook called to perform a frame operation with the
    current scene
    """

    def get_frame_range(self, **kwargs):
        """
        get_frame_range will return a tuple of (in_frame, out_frame)

        :returns: Returns the frame range in the form (in_frame, out_frame)
        :rtype: tuple[int, int]
        """
        app = self.parent
        engine = sgtk.platform.current_engine()
        dcc_app = engine.app

        frame_range = dcc_app.get_frame_range()

        start_frame = frame_range.get("start_frame", 0)
        stop_frame = frame_range.get("stop_frame", 0)

        return (start_frame, stop_frame)

    def set_frame_range(self, in_frame=None, out_frame=None, **kwargs):
        """
        set_frame_range will set the frame range using `in_frame` and `out_frame`

        :param int in_frame: in_frame for the current context
            (e.g. the current shot, current asset etc)

        :param int out_frame: out_frame for the current context
            (e.g. the current shot, current asset etc)

        """

        # In Harmony, everything seems to start at frame 1 so
        # we are just adjusting the duration to fit the range and
        # and setting start and the stop frame.
        #
        # Please adjust this logic accordingly to however you want to handle
        # frame ranges in your pipeline
        app = self.parent
        engine = sgtk.platform.current_engine()
        dcc_app = engine.app

        # add frames if needed
        target_frame_duration = out_frame - in_frame + 1
        dcc_app.set_frame_count(out_frame)

        # set range
        dcc_app.set_start_frame(in_frame)
        dcc_app.set_stop_frame(out_frame)
