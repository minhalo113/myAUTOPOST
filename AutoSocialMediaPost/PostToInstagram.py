# import requests
# import webbrowser
# from flask import Flask, request
# import threading
# from config import INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, REDIRECT_URL
# import sys, os

# app = Flask(__name__)
# app_id = INSTAGRAM_APP_ID
# app_secret = INSTAGRAM_APP_SECRET
# redirect_url = REDIRECT_URL
# authorization_code = None

# def getAccessToken():
#     global authorization_code

#     permissions = "pages_show_list,pages_manage_posts"

#     oauth_url = (
#         f"https://www.facebook.com/v21.0/dialog/oauth?"
#         f"client_id={app_id}&redirect_uri={redirect_url}&scope={permissions}&response_type=code"
#     )

#     webbrowser.open(oauth_url)
#     redirected_url = input("Redirected URL: ")

#     try:
#         authorization_code = redirected_url.split("code=")[1]

#         token_exchange_url = (
#             f"https://graph.facebook.com/v21.0/oauth/access_token?"
#             f"client_id={app_id}&redirect_uri={redirect_url}&client_secret={app_secret}&code={authorization_code}"
#         )
#         response = requests.get(token_exchange_url)
#         response_data = response.json()

#         if "access_token" in response_data:
#             access_token = response_data["access_token"]
#             return access_token
#         else:
#             print(f"Error: {response_data.get('error', 'Unknown error')}")
#             return None

#     except Exception as e:
#         print(f"Error extracting authorization code: {e}")
#         return None
dsafsadf