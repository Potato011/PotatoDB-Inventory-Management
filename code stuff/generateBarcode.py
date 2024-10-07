import barcode
from barcode.writer import ImageWriter
import os

# Define the directory to save barcodes
BARCODE_DIR = 'static/barcodes'

# Ensure the directory exists
os.makedirs(BARCODE_DIR, exist_ok=True)


def get_barcodes(unique_id):
    # Use the unique identifier to generate a 12-digit barcode content (left-padded with zeros if necessary)
    barcode_content = str(unique_id).zfill(12)
    # print(unique_id)
    # Specify the type of barcode you want to generate, for example EAN13
    barcode_class = barcode.get_barcode_class('ean13')

    # Generate the barcode with image writer
    ean = barcode_class(barcode_content, writer=ImageWriter())

    # Use the full barcode (including the checksum) for the filename
    full_code = ean.get_fullcode()

    # Define the full path where the barcode will be saved
    filename = os.path.join(BARCODE_DIR, full_code)

    # Save the barcode as an image file with the full barcode content as the filename
    ean.save(filename)

    # Return the path to the saved barcode image and the barcode content
    print(full_code)
    return f"{filename}.png", full_code


# Example usage
if __name__ == "__main__":
    # Replace this with a unique identifier as an example
    barcode_image_path, barcode_number = get_barcodes(781234567890)
    print(f"Barcode saved as {barcode_image_path} with content {barcode_number}")
