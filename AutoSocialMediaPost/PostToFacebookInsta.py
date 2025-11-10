import requests
import webbrowser
from flask import Flask, request
import threading
from config import (FACEBOOK_APP_SECRET, FACEBOOK_APP_ID, REDIRECT_URL, IGMUR_CLIENT_ID,
X_API_KEY, X_API_SECRET_KEY, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
STORELINK, X_CLIENT_ID, X_CLIENT_SECRET, ACCESS_TOKEN_SHOPIFY, STORELINKFORSHOPIFYAPI, SHOPIFY_YOUR_NEXT_READ_BLOG_ID)
import sys, os

import http.server
import socketserver
import subprocess
import time 
import json
import tweepy
from datetime import datetime

from requests_oauthlib import OAuth1Session

app = Flask(__name__)
app_id = FACEBOOK_APP_ID
app_secret = FACEBOOK_APP_SECRET
redirect_url = REDIRECT_URL
igmur_client_id = IGMUR_CLIENT_ID

x_api_key = X_API_KEY
x_api_secret_key = X_API_SECRET_KEY
x_access_token = X_ACCESS_TOKEN
x_access_token_secret = X_ACCESS_TOKEN_SECRET

blog_id = SHOPIFY_YOUR_NEXT_READ_BLOG_ID

authorization_code = None

def create_public_server(photo_path):
    url = "https://api.imgur.com/3/image"
    headers = {"Authorization": f"Client-ID {igmur_client_id}"}
    files = {"image": open(photo_path, "rb")}
    
    try:
        response = requests.post(url, headers=headers, files=files)
        if response.status_code == 200:
            image_url = response.json()["data"]["link"]
            return image_url
        else:
            print(f"Error uploading image to igmur: {response.status_code}, {response.text}")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        files["image"].close()


def get_insta_account_id(access_token):
    try:
        pages_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={access_token}"
        pages_response = requests.get(pages_url).json()
        page_id = pages_response["data"][0]["id"]

        instagram_url = f"https://graph.facebook.com/v21.0/{page_id}?fields=instagram_business_account&access_token={access_token}"
        instagram_response = requests.get(instagram_url).json()

        if "instagram_business_account" in instagram_response:
            instagram_id = instagram_response["instagram_business_account"]["id"]
            return instagram_id
        else:
            print("Instagram Business Account not linked to the page.")
    except Exception as e:
        print(f"An error occurred 1: {e}")

def post_to_instagram(image_path, caption, insta_account_id, access_token):
    upload_url = f"https://graph.facebook.com/v21.0/{insta_account_id}/media"
    public_image_path = create_public_server(image_path)
    data = {
        "image_url": public_image_path,
        "access_token": access_token,
        "caption": caption,
    }

    response = requests.post(upload_url, data= data)
    upload_response = response.json()

    if "id" not in upload_response:
        print(f"Error uploading image: {upload_response.get('error', 'Unknown error')}")
        return public_image_path

    media_id = upload_response["id"]
    print(f"Media uploaded successfully. Media ID: {media_id}")

    publish_url = f"https://graph.facebook.com/v21.0/{insta_account_id}/media_publish"
    publish_response = requests.post(
        publish_url,
        data={
            "creation_id": media_id,
            "access_token": access_token,
        },
    )
    publish_response_data = publish_response.json()

    if "id" in publish_response_data:
        print(f"Post published to Insta successfully. Post ID: {publish_response_data['id']}")
    else:
        print(f"Error publishing post: {publish_response_data.get('error', 'Unknown error')}")
    return public_image_path

def getAccessToken():
    global authorization_code

    permissions = "pages_show_list,pages_manage_posts"

    oauth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={app_id}&redirect_uri={redirect_url}&scope={permissions}&response_type=code"
    )

    webbrowser.open(oauth_url)
    redirected_url = input("Redirected URL: ")

    try:
        authorization_code = redirected_url.split("code=")[1]

        token_exchange_url = (
            f"https://graph.facebook.com/v21.0/oauth/access_token?"
            f"client_id={app_id}&redirect_uri={redirect_url}&client_secret={app_secret}&code={authorization_code}"
        )
        response = requests.get(token_exchange_url)
        response_data = response.json()

        if "access_token" in response_data:
            access_token = response_data["access_token"]
            already_get_token = True
            return access_token
        else:
            print(f"Error: {response_data.get('error', 'Unknown error')}")
            return None

    except Exception as e:
        print(f"Error extracting authorization code: {e}")
        return None

def getUserId(access_token):
    url = f"https://graph.facebook.com/v21.0/me?fields=id,name&access_token={access_token}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        user_id = data.get("id")
        return user_id
    else:
        print(f"Error fetching User ID: {response.status_code} - {response.text}")
        return None

def getPageInfo(user_id, access_token):
    url_page_access_token = f"https://graph.facebook.com/{user_id}/accounts?access_token={access_token}"
    response = requests.get(url_page_access_token)

    if response.status_code == 200:
        data = response.json()

        if data.get('data'):
            first_page = data['data'][0]
            page_id = first_page.get('id')
            page_access_token = first_page.get('access_token')
            
            if page_id and page_access_token:
                return page_id, page_access_token

    else:
        print(f"Error fetching Page Access Token: {response.status_code} - {response.text}")
        return None


def posting(message, page_id, page_access_token):
    post_message = message
    headers = {
        'Content-Type': 'application/json',
    }
    data = '{"message":"' + post_message + '"}'
    post_url = f"https://graph.facebook.com/v21.0/{page_id}/feed?access_token={page_access_token}"

    response = requests.post(post_url, headers = headers, data=data)

    if response.status_code == 200:
        print("Post published successfully (text_only):", response.json())
    else:
        print("Error publishing post:", response.text)


def post_photo_to_facebook(page_id, photo_path, page_access_token, caption):
    try:
        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"

        with open(photo_path, "rb") as photo_file:

            data = {
                "access_token": page_access_token,
                "message": caption,
            }
            files = {
                "source": photo_file,
            }

            response = requests.post(url, data=data, files=files)
            response_data = response.json()

        if "id" in response_data:
            print(f"Posted To Facebook! Post ID: {response_data['id']}")
        else:
            print(f"Failed to post photo: {response_data}")
    except Exception as e:
        print(f"An error occurred 3: {e}")


def post_to_X(photo_path, caption):
    auth = tweepy.OAuth1UserHandler(
        consumer_key=x_api_key,
        consumer_secret=x_api_secret_key,
        access_token=x_access_token,
        access_token_secret=x_access_token_secret
    )
    api = tweepy.API(auth, wait_on_rate_limit=True)

    media = api.media_upload(photo_path)

    client = tweepy.Client(
        consumer_key=x_api_key,
        consumer_secret=x_api_secret_key,
        access_token=x_access_token,
        access_token_secret=x_access_token_secret
    )

    response = client.create_tweet(
        text=caption,
        media_ids=[media.media_id]
    )

    print(f"Posted to X: {response.data['id']}")

def shopify_api_create_blog():
    global blog_id

    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': ACCESS_TOKEN_SHOPIFY,
    }

    
    data = '{\n"query": "mutation CreateBlog($blog: BlogCreateInput!) { blogCreate(blog: $blog) \
        { blog { id title handle templateSuffix commentPolicy } userErrors { code field message } } }",\n "variables": {\n    "blog": {\n    \
                "title": "Your Next Reatd",\n      "handle": "your-next-read",\n      "templateSuffix": "standard",\n      "commentPolicy": "MODERATED"\n    }\n  }\n}'

    response = requests.post(f"{STORELINKFORSHOPIFYAPI}",
                             headers=headers,
                             data = data,
                             )

    if response.status_code == 200:
        data = response.json()
        print(data)
        # blog_id = str(data["blog"][0]["id"])
        # print(blog_id)
    else:
        print("Error:", response.status_code, response.text)

def change_title_to_handle(title):
    return title.replace(" ", "-").lower()

def post_article_to_blog(title, message, photo_path):

    shopify_headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': ACCESS_TOKEN_SHOPIFY,
    }
    
    publish_date = datetime.now().isoformat()
    article_data = {
                    'blogId': f'gid://shopify/Blog/{blog_id}',
                    'title': title,
                    'author': {
                        'name': 'Michael Luong',
                    },
                    'handle': change_title_to_handle(title),
                    'body': message,
                    'isPublished': True,
                    'publishDate': publish_date,
                }
    
    if photo_path:
        article_data["image"] = {
            "url": photo_path
        }

    json_data = {
        'query': 'mutation CreateArticle($article: ArticleCreateInput!) { articleCreate(article: $article) { article { id title author { name } handle body summary tags image { altText originalSrc } } userErrors { code field message } } }',
        'variables': {'article': article_data},
    }
    json_data = json.dumps(json_data, indent=4)

    response = requests.post(f"{STORELINKFORSHOPIFYAPI}",
                             headers=shopify_headers,
                             data = json_data,
                             )
    

    if response.status_code == 200:
        print(f"Posted blog to shop")
    else:
        print("Error:", response.status_code, response.text)


def post_blog(photo_path, caption, already_got_token, access_token, user_id, page_id, page_access_token, insta_account_id, title):
    if already_got_token == False:
        access_token = getAccessToken()
        user_id = getUserId(access_token)
        page_id, page_access_token = getPageInfo(user_id, access_token)
        insta_account_id = get_insta_account_id(access_token)
    else:
        access_token = access_token
        user_id = user_id
        page_id = page_id
        page_access_token = page_access_token
        insta_account_id = insta_account_id
    
    message = caption
    if photo_path == '':
        posting(message, page_id, page_access_token)
        post_article_to_blog(title, message, photo_path)
    else:
        post_photo_to_facebook(page_id, photo_path, page_access_token, message)
        public_image_url = post_to_instagram(photo_path, message, insta_account_id, access_token)
        post_article_to_blog(title, message, public_image_url)

    return access_token, user_id, page_id, page_access_token, insta_account_id

def main(photo_path, caption, already_got_token, access_token, user_id, page_id, page_access_token, insta_account_id):

    if already_got_token == False:
        access_token = getAccessToken()
        user_id = getUserId(access_token)
        page_id, page_access_token = getPageInfo(user_id, access_token)
        insta_account_id = get_insta_account_id(access_token)
    else:
        access_token = access_token
        user_id = user_id
        page_id = page_id
        page_access_token = page_access_token
        insta_account_id = insta_account_id

    message = caption

    if photo_path == '':
        posting(message, page_id, page_access_token)
        return
    else:
        print( "Page Id: ", page_id)
        print("insta account id", insta_account_id)
        post_photo_to_facebook(page_id, photo_path, page_access_token, message)
        post_to_instagram(photo_path, message, insta_account_id, access_token)
        post_to_X(photo_path, caption)
    return access_token, user_id, page_id, page_access_token, insta_account_id

