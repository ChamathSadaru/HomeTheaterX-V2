import asyncio
import sys

async def main():
    import winrt.windows.media.control as wmc
    manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = manager.get_current_session()
    if not session:
        print("No active media session found.")
        return

    props = await session.try_get_media_properties_async()
    pb = session.get_playback_info()
    timeline = session.get_timeline_properties()

    print("Title:", props.title if props else "N/A")
    print("Artist:", props.artist if props else "N/A")
    print("Source App ID:", session.source_app_user_model_id)
    print("Playback Info:", pb.playback_status if pb else "N/A")
    if timeline:
        print("Timeline pos:", timeline.position.total_seconds() if timeline.position else None)
        print("Timeline end_time:", timeline.end_time.total_seconds() if timeline.end_time else None)
        print("Timeline last_updated:", timeline.last_updated_time if hasattr(timeline, 'last_updated_time') else None)
    else:
        print("Timeline: None")

if __name__ == "__main__":
    asyncio.run(main())
