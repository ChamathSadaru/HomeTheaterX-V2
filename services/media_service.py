import base64

async def get_windows_media_status():
    """Fetches real-time media metadata, playback status, position, and base64 album artwork from Windows."""
    import winrt.windows.media.control as wmc
    import winrt.windows.storage.streams as wss
    try:
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return {"status": "no_session"}
        
        props = await session.try_get_media_properties_async()
        pb = session.get_playback_info()
        timeline = session.get_timeline_properties()
        
        status_val = int(pb.playback_status) if pb else 0
        pos = 0.0
        dur = 0.0
        if timeline:
            try:
                if timeline.position is not None:
                    pos = float(timeline.position.total_seconds())
            except Exception:
                pass
            try:
                if timeline.end_time is not None:
                    dur = float(timeline.end_time.total_seconds())
            except Exception:
                pass
        
        thumbnail_b64 = ""
        if props and props.thumbnail:
            try:
                stream = await props.thumbnail.open_read_async()
                size = stream.size
                if size > 0:
                    reader = wss.DataReader(stream.get_input_stream_at(0))
                    await reader.load_async(size)
                    data_bytes = bytearray(size)
                    reader.read_bytes(data_bytes)
                    thumbnail_b64 = base64.b64encode(data_bytes).decode('utf-8')
            except Exception:
                pass

        return {
            "status": "success",
            "title": props.title if props else "Unknown Title",
            "artist": props.artist if props else "Unknown Artist",
            "playback_status": status_val,
            "position": pos,
            "duration": dur,
            "thumbnail": thumbnail_b64,
            "source": session.source_app_user_model_id or ""
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def control_windows_media(action, position_seconds=None):
    """Sends control commands (play/pause, next, previous, seek) to the active Windows media session."""
    import winrt.windows.media.control as wmc
    try:
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if not session:
            return False
        
        if action == "play_pause":
            return await session.try_toggle_play_pause_async()
        elif action == "next":
            return await session.try_next_async()
        elif action == "previous":
            return await session.try_previous_async()
        elif action == "seek" and position_seconds is not None:
            # TimeSpan in 100-nanosecond ticks
            ticks = int(float(position_seconds) * 10_000_000)
            return await session.try_change_playback_position_async(ticks)
        return False
    except Exception as e:
        print("Error sending media control:", e)
        return False
