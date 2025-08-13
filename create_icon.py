#!/usr/bin/env python3
"""
Create Windows icon file from the tray image
"""

import os
from PIL import Image, ImageDraw

def create_tray_image():
    """Create the same icon as used in the GUI"""
    # Create a simple icon image
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), color='blue')
    draw = ImageDraw.Draw(image)
    
    # Draw a simple "T" for Telegram
    draw.rectangle([20, 10, 30, 50], fill='white')
    draw.rectangle([10, 10, 50, 20], fill='white')
    
    return image

def create_icon_file():
    """Create .ico file for Windows executable"""
    try:
        # Create assets directory
        os.makedirs('assets', exist_ok=True)
        
        # Create base image
        base_image = create_tray_image()
        
        # Create multiple sizes for ICO file
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        images = []
        
        for size in icon_sizes:
            resized = base_image.resize(size, Image.Resampling.LANCZOS)
            images.append(resized)
        
        # Save as ICO file
        ico_path = os.path.join('assets', 'icon.ico')
        images[0].save(ico_path, format='ICO', sizes=icon_sizes, append_images=images[1:])
        
        print(f"✅ Icon file created: {ico_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create icon: {e}")
        return False

if __name__ == "__main__":
    create_icon_file()