import os
import sys
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

YOUTUBE_CHANNELS = {
    "A History A Day": "https://studio.youtube.com/channel/UC5DgbuRf_2ZJgjL4uir6MzA",

}

def get_browser_profile_dir(channel_name: str) -> Path:
    if os.name == 'nt':
        local_app_data = os.getenv('LOCALAPPDATA', '')
        if not local_app_data:
            local_app_data = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        local_app_data = os.path.join(os.path.expanduser('~'), '.config')
        
    safe_name = "".join([c if c.isalnum() else "_" for c in channel_name])
    user_data_dir = Path(local_app_data) / "SocialUploader" / f"BrowserProfile_{safe_name}"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return user_data_dir

def setup_youtube_login(channel_name: str, channel_url: str) -> None:
    """Opens a persistent Edge browser window to allow the user to manually log in."""
    user_data_dir = get_browser_profile_dir(channel_name)
    
    if os.name == 'nt':
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if not os.path.exists(edge_path):
            edge_path = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
            
        if os.path.exists(edge_path):
            cmd = f'"{edge_path}" --user-data-dir="{user_data_dir}" "{channel_url}"'
            subprocess.Popen(cmd, shell=True)
            return
            
    print("Launching Playwright to allow manual login...")
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="msedge"
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(channel_url)
        print("Please log into your YouTube account in the browser that just opened.")
        print("Once you are successfully logged in and can see your YouTube Studio dashboard, completely close that browser window.")
        page.wait_for_event("close", timeout=0)
        browser.close()

def upload_to_youtube(video_path: Path, title: str, description: str, channel_name: str, channel_url: str) -> None:
    """Automates uploading a video to YouTube Studio using Playwright."""
    if not video_path.exists():
        raise FileNotFoundError(f"The video file could not be found: {video_path}")
        
    user_data_dir = get_browser_profile_dir(channel_name)
    print(f"Starting YouTube Upload automation for {channel_url}...")
    
    with sync_playwright() as p:
        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="msedge"
        )
        
        try:
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            
            page.set_default_timeout(60000)
            
            page.goto(channel_url)
            
            create_button_selector = "ytcp-button-shape[aria-label='Create'] button, button[aria-label='Create']"
            page.wait_for_selector(create_button_selector, state="visible", timeout=0)
            page.click(create_button_selector)
            print("Successfully clicked the 'Create' button.")

            upload_videos_selector = "yt-formatted-string.item-text.main-text:has-text('Upload videos')"
            page.wait_for_selector(upload_videos_selector, state="visible")
            page.click(upload_videos_selector)
            print("Successfully clicked 'Upload videos'.")

            file_input_selector = "input[type='file']"
            page.wait_for_selector(file_input_selector, state="attached")
            page.set_input_files(file_input_selector, str(video_path))
            print(f"Successfully attached video file to YouTube: {video_path}")

            title_selector = "div[aria-label*='Add a title that describes your video']"
            page.wait_for_selector(title_selector, state="visible")
            page.locator(title_selector).fill(title)
            print("Successfully entered the YouTube title.")

            description_selector = "div[aria-label*='Tell viewers about your video']"
            page.wait_for_selector(description_selector, state="visible")
            page.locator(description_selector).fill(description)
            print("Successfully entered the YouTube description.")

            page.wait_for_timeout(3000)

            not_for_kids_selector = "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"
            page.wait_for_selector(not_for_kids_selector, state="visible")
            page.locator(not_for_kids_selector).click()
            print("Clicked 'No, it is not made for kids'.")

            visibility_step_selector = "button#step-badge-3"
            page.wait_for_selector(visibility_step_selector, state="visible")
            page.locator(visibility_step_selector).click()
            print("Clicked 'Visibility' stepper.")

            public_visibility_selector = "tp-yt-paper-radio-button[name='PUBLIC']"
            page.wait_for_selector(public_visibility_selector, state="visible")
            page.locator(public_visibility_selector).click()
            print("Clicked 'Public' visibility.")

            # Click "Publish" button
            # publish_button_selector = "button[aria-label='Publish'], ytcp-button#done-button"
            # page.wait_for_selector(publish_button_selector, state="visible")
            # page.locator(publish_button_selector).click()
            # print("Clicked 'Publish' button. Waiting for upload to finish...")
            
            # print("Waiting for upload to complete... Please do not close the browser.")
            # try:
            #     page.wait_for_selector("ytcp-video-upload-progress:not([uploading])", timeout=1800000)
            # except Exception as wait_e:
            #     print(f"Warning during upload wait: {wait_e}. Upload might not have finished.")
                
            # page.wait_for_timeout(5000)
            
            # print("Video uploaded and published successfully!")
            
        except Exception as e:
            print(f"YouTube Automation Error: {e}")
            raise
        # finally:
            # browser_context.close()

if __name__ == "__main__":
    # Test script run
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        setup_youtube_login("A History A Day", YOUTUBE_CHANNELS["A History A Day"])
