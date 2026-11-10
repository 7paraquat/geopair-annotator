"""Generate artificial images for learning the UI; not real remote-sensing data."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent/'demo_dataset/Demo-City/images'
for modality in ('RGB_png','SAR_png'):
    folder=root/modality; folder.mkdir(parents=True,exist_ok=True)
    optical=modality=='RGB_png'
    image=Image.new('RGB',(512,512),(45,70,48) if optical else (45,45,45))
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,210,512,265),fill=(95,95,95) if optical else (18,18,18))
    draw.rectangle((45,60,170,170),fill=(200,180,140) if optical else (210,210,210))
    draw.rectangle((300,320,450,435),fill=(160,170,190) if optical else (155,155,155))
    draw.text((10,485),'SYNTHETIC DEMO - NOT REAL SAR',fill='white')
    image.save(folder/'sample_001.png')
print(root.parent.parent)
