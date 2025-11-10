import tkinter as tk
from tkinter import filedialog, messagebox
from AutoCreateContentForWeb.GetTranscript import long_form_video_transcript_vi, long_form_video_transcript_en
from AutoSocialMediaPost import PostToFacebookInsta
from AutoCreateMotivationalQuotes.AutoMotivationalQuotes import create_posts
from config import STORELINK
import sys

root = tk.Tk()
image_path = tk.StringVar()
caption_text = tk.Text(root, width=50, height=5)
title_text = tk.Text(root, width=50,height=5 )
already_got_token = False
access_token, user_id, page_id, page_access_token, insta_account_id = None, None, None, None, None
video_url = tk.Text(root, width = 50, height = 2)

def select_image():
    global image_path
    global caption_text
    file_path = filedialog.askopenfilename(
        title="Select Image",
        filetypes=(("Image Files", "*.png;*.jpg;*.jpeg"), ("All Files", "*.*")),
    )
    if file_path:
        image_path.set(file_path)
    else:
        image_path = None

def post_image():
    global image_path
    global caption_text
    global already_got_token
    global access_token, user_id, page_id, page_access_token, insta_account_id

    img_path = image_path.get()
    caption = caption_text.get("1.0", tk.END).strip()

    if img_path == "":
        img_path = create_posts()
        if caption == "":
            #caption = "Get inspired and find your next great read to improve yourself at our bookstore: " + STORELINK
            caption = ""
        access_token, user_id, page_id, page_access_token, insta_account_id = PostToFacebookInsta.main(img_path, caption, already_got_token, access_token, user_id, page_id, page_access_token, insta_account_id)
    else:
        access_token, user_id, page_id, page_access_token, insta_account_id = PostToFacebookInsta.main(img_path, caption, already_got_token, access_token, user_id, page_id, page_access_token, insta_account_id)

    if already_got_token == False:
        already_got_token = True

def post_blog():
    global image_path
    global caption_text
    global already_got_token
    global access_token, user_id, page_id, page_access_token, insta_account_id
    global title_text

    img_path = image_path.get()
    caption = caption_text.get("1.0", tk.END).strip()
    title = title_text.get("1.0", tk.END).strip()

    access_token, user_id, page_id, page_access_token, insta_account_id = PostToFacebookInsta.post_blog(img_path, caption, already_got_token, access_token, user_id, page_id, page_access_token, insta_account_id, title)

def get_long_video_script_vi():
    global video_url
    print(video_url.get("1.0", "end-1c").strip())
    return long_form_video_transcript_vi(video_url.get("1.0", "end-1c").strip())

def get_long_video_script_en():
    global video_url
    print(video_url.get("1.0", "end-1c").strip())
    return long_form_video_transcript_en(video_url.get("1.0", "end-1c").strip())

def main():
    global image_path
    global caption_text
    global title_text
    root.title("Auto Poster")

    tk.Label(root, text="Image:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    image_entry = tk.Entry(root, textvariable=image_path, width=50)
    image_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")
    tk.Button(root, text="Browse", command=select_image).grid(row=0, column=2, padx=10, pady=10)



    tk.Label(root, text="Title:").grid(row=1, column=0, padx=10, pady=10, sticky="nw")
    title_text.grid(row=1, column=1, padx=10, pady=10, sticky="w")

    tk.Label(root, text="Caption:").grid(row=2, column=0, padx=10, pady=10, sticky="nw")
    caption_text.grid(row=2, column=1, padx=10, pady=10, sticky="w")

    tk.Button(root, text= "Post Blog to Facebook and Shopify and Instagram", command = post_blog).grid(row = 3, column=1, pady = 20)

    tk.Button(root, text="Post to Facebook Insta and X", command=post_image).grid(row=4, column=1, pady=20)

    video_url.grid(row = 5, column=1, padx=10, pady=10, sticky="w")
    tk.Button(root, text = "Get Long Video Script VI", command = get_long_video_script_vi).grid(row = 6, column = 1, pady=20)

    tk.Button(root, text = "Get Long Video Script EN", command = get_long_video_script_en).grid(row = 7, column = 1, pady=20)
    root.mainloop()

main()


