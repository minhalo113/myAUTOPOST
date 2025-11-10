from AutoCreateContentForWeb.ScrapeContent import return_videos_list
from youtube_transcript_api import YouTubeTranscriptApi
from huggingface_hub import InferenceClient
from config import API_HUGGINGFACE_KEY, OPENAI_KEY;
import json

from openai import OpenAI
client = OpenAI(api_key=OPENAI_KEY)

def write_video_ids_to_file(video_id, filename = 'AutoCreateContentForWeb/already_use_video.txt'):
    with open(filename, 'a') as f:
        f.write(video_id + "\n")

def test_to_file(video_id, filename = 'test.txt'):
    with open(filename, 'a', encoding = 'utf-8') as f:
        f.write(video_id + "\n\n\n")

def revise_script(text):
    # single call → both essay & title
    resp = client.chat.completions.create(
        model="gpt-5-nano",
        response_format={"type": "json_object"}, 
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional long-form essay writer. "
                    "Deliver detailed, structured essays without any casual conversation, greetings, or offers to expand. "
                    "You will revise the input not to do anything more"
                    "Do not refer to yourself or the user. Start immediately with the content. "
                    "Maintain a formal, academic tone throughout."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Return a JSON object with exactly two fields:\n"
                    "  - essay: a long-form, detailed essay of at least 2000 tokens revised the following input, you should keep the content.\n"
                    "           End with a concluding section tying back the overall theme.\n"
                    "  - title: a single concise, compelling title for that essay (no quotes, no extra text).\n"
                    "\nINPUT:\n" + text
                ),
            },
        ],
        temperature=1,
    )

    data = json.loads(resp.choices[0].message.content)
    refined_text = data.get("essay", "")
    title = data.get("title", "")
    revised_text = "currently stop working"  # keep your placeholder

    return [refined_text, title, revised_text]

# def revise_script(text):
#     # use model to revise script
#     text = "Tell me more about this, make sure your output is at least 2000 tokens: " + text
#     api_key = API_HUGGINGFACE_KEY

#     refined_text =[]
#     title = []
#     revised_text = []

#     client = InferenceClient(
#         "HuggingFaceH4/zephyr-7b-beta",
#         token=api_key,
#     )

#     for message in client.chat_completion(
#         messages=[{"role": "user", "content": text}],
#         max_tokens=2048,
#         stream=True
#     ):  
#         refined_text.append(message.choices[0].delta.content)
#     refined_text = "".join(refined_text)
    
#     for message in client.chat_completion(
#         messages=[{"role": "user", "content": 
#                    "Create only one title for this paragraph, only answer the title, do not add any unnecessary word:" + refined_text}],
#         max_tokens=50,
#         stream=True,
#         temperature=0.1
#     ):  
#         title.append(message.choices[0].delta.content)
#     title = "".join(title)

#     for message in client.chat_completion(
#         messages=[{"role": "user", "content": 
#                    "Revise this text but keep it content:" + text}],
#         max_tokens=2048,
#         stream=True,
#         temperature=0.6
#     ):  
#         revised_text.append(message.choices[0].delta.content)
#     revised_text = "".join(revised_text)

#     return  [refined_text, title, revised_text]

def extract_video_id(url):
    if "watch?v=" in url:
        return url.split('watch?v=')[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split('youtu.be/')[-1].split("?")[0]
    return None

def long_form_video_transcript_en(url):
    videoID = extract_video_id(url)
    script = ""
    if not videoID:
        return
    try:
        ytt_api = YouTubeTranscriptApi()
        get_transcript = ytt_api.fetch(videoID, languages=['en', 'en'])
        transcript = get_transcript.to_raw_data()

        for entry in transcript:
            script += " " + entry["text"]

        test_to_file(script, "LongVideoScript.txt")
    except Exception as e:
        print("Error :", e)

def long_form_video_transcript_vi(url):
    videoID = extract_video_id(url)
    script = ""
    if not videoID:
        return
    try:
        ytt_api = YouTubeTranscriptApi()
        get_transcript = ytt_api.fetch(videoID, languages=['en', 'vi'])
        transcript = get_transcript.to_raw_data()

        for entry in transcript:
            script += " " + entry["text"]

        test_to_file(script, "LongVideoScript.txt")
    except Exception as e:
        print("Error :", e)

def get_transcript():
    video = return_videos_list()
    write_video_ids_to_file(video['video_id'])
    script = ""

    # get script through audio
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video['video_id'])
        transcript = transcript.to_raw_data()
        for entry in transcript:
            script = script + " " + entry["text"]

    except Exception as e:
        print("Error :", e)

    # # revise script
    test_to_file(script, "AutoCreateContentForWeb/true_script_for_vid_1.txt")
    [finalize_script, title, revised_text] = revise_script(script)
    test_to_file(revised_text, "AutoCreateContentForWeb/script_for_vid.txt")
    return [script, finalize_script, title]

if __name__ == "__main__":
    long_form_video_transcript("https://www.youtube.com/watch?v=RPn0PiLsAMM")