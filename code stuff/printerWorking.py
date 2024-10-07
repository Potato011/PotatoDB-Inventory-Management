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
    target_width = 2 * 203  # 2 inches * 203 dots per inch
    target_height = 1 * 203  # 1 inch * 203 dots per inch
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
    HORZRES = 8
    VERTRES = 10
    printable_area = hdc.GetDeviceCaps(HORZRES), hdc.GetDeviceCaps(VERTRES)

    # Draw the image
    dib = ImageWin.Dib(Image.open(temp_image_path))
    dib.draw(hdc.GetHandleOutput(), (0, 0, printable_area[0], printable_area[1]))

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
