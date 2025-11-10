import os
import random
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random

background_folder = "AutoCreateMotivationalQuotes/backgrounds/"
output_folder = "AutoCreateMotivationalQuotes/output/"
quotes_file = "AutoCreateMotivationalQuotes/quotes.txt"
font_directories = "C:\Windows\Fonts"
alreadymade_post = "AutoCreateMotivationalQuotes/alreadymade_post/"

all_font = []

def get_fonts():
    if os.path.exists(font_directories):
        for root, _, files in os.walk(font_directories):
            for file in files:
                if file.endswith(".ttf") or file.endswith(".otf"):
                    all_font.append(os.path.join(root, file))

def get_random_background(folder):
    files = os.listdir(folder)
    return os.path.join(folder, random.choice(files))

def get_random_quote(file_path):
    with open(file_path, "r") as file:
        quotes = file.readlines()
    return random.choice(quotes).strip()

def create_motivational_image(background_path, quote, output_path):
    font_scale = 1.8

    image = Image.open(background_path)

    grayscale_image = image.convert("L")
    image = grayscale_image.convert("RGB")

    draw = ImageDraw.Draw(image)
    
    get_fonts()

#----------------------------filtered font
    not_good_fonts = ["C:\Windows\Fonts\segoeuiz.ttf", "C:\Windows\Fonts\sylfaen.ttf", "C:\Windows\Fonts\holomdl2.ttf","C:\Windows\Fonts\webdings.ttf", "C:\Windows\Fonts\consola.ttf"]
    filtered_fonts = [font for font in all_font if font not in not_good_fonts]
#----------------------------filtered font
    font_path = random.choice(filtered_fonts)

    print(font_path)
    print(background_path)

    width, height = image.size
    font_size = int(height * 0.05)

# --------------------------------------------------Font Specific
    # if font_path == "consola.ttf":
    #     font_size = font_size * 0.6
    # if font_path == "comicbd.ttf":
    #     font_size = font_size * 0.4
    # if font_path == "georgiab.ttf":
    #     font_size = font_size * 0.4
# --------------------------------------------------Font Specific
    #font_path = "consola.ttf"

    font_color = "white"
    font = ImageFont.truetype(font_path, font_size)

    max_width = int(width * 0.86)
    wrapped_quote = textwrap.fill(quote, width = int(max_width/font_size * font_scale))

    lines = wrapped_quote.split("\n")
    _, _, _, line_height = draw.textbbox((0, 0), text = lines[0], font = font)
    line_height += 30
    total_text_height = line_height * len(lines)

    y_start = (height - total_text_height) /2 

    for line in lines:
        _, _, text_width, _ = draw.textbbox((0, 0), text = line, font = font)
        x = (width - text_width) /2
        draw.text((x, y_start), line, font = font, fill= font_color)
        y_start += line_height
    
    output_file = os.path.join(output_path, f"motivational_{random.randint(1000, 9999)}.jpg")
    image.save(output_file)
    print(f"Image saved to {output_file}")
    return output_file

def create_posts():
    result = random.choice([True, False])

    if result == True:
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        
        background = get_random_background(background_folder)
        quote = get_random_quote(quotes_file)
        output_file_path = create_motivational_image(background, quote, output_folder)
        return output_file_path
    else:
        files = os.listdir(alreadymade_post)
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif')
        image_files = [file for file in files if file.lower().endswith(image_extensions)]

        random_image = random.choice(image_files)
        random_image_path = os.path.join(alreadymade_post, random_image)
        return random_image_path

if __name__ == "__main__":
    create_posts()