from string import printable

from PIL import Image
import os
import win32print
import win32ui
from PIL import ImageWin


def print_label(image_path, printer_name=None):
    # Normalize the image path to handle different path formats
    image_path = os.path.normpath(image_path)

    # Check if the image file exists and is accessible
    if not os.path.isfile(image_path):
        print(f"Error: The file at {image_path} does not exist or is not a file.")
        return

    # Load the image
    try:
        image = Image.open(image_path)
    except Exception as e:
        print(f"An error occurred while opening the image: {e}")
        return

    # Resize image to fit the 2"x1" label (203 DPI assumed for label printers)
    target_width = int(2 * 203)
    target_height = int(1 * 203)
    image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Convert image to BMP format (since Windows printing works well with BMP)
    temp_image_path = os.path.join(os.getcwd(), "temp_image.bmp")
    image.save(temp_image_path, "BMP")

    # Get the printer handle
    if printer_name is None:
        printer_name = win32print.GetDefaultPrinter()

    # Start printing
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    hdc.StartDoc("Barcode Label")
    hdc.StartPage()

    # Get printable area
    HORZRES = 406  # 2 inches at 203 DPI
    VERTRES = 203  # 1 inch at 203 DPI
    offset_x = 200
    # Set the printable area to a fixed 2"x1"
    printable_area = HORZRES, VERTRES

    #print("printable area horizontal: ", printable_area[0], "printable area vertical: ", printable_area[1])

    # Draw the image
    dib = ImageWin.Dib(Image.open(temp_image_path))
    dib.draw(hdc.GetHandleOutput(), (offset_x, 0, offset_x + HORZRES, VERTRES))

    hdc.EndPage()
    hdc.EndDoc()
    hdc.DeleteDC()

    # Clean up temporary BMP file
    os.remove(temp_image_path)

    print(f"Image sent to {printer_name} successfully.")


if __name__ == "__main__":
    # Get image path and printer name from user
    image_path = input("Enter the path to the image: ").strip()
    printer_name = input("Enter the printer name (leave blank for default): ").strip()

    print_label(image_path, printer_name)
