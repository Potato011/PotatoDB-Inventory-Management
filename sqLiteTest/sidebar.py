
import json
import platform
import subprocess

# Function to get a unique FIND value using the `id_tracker` table
def get_unique_find(connection):
    cur = connection.cursor()
    cur.execute('INSERT INTO id_tracker DEFAULT VALUES;')
    connection.commit()
    return cur.lastrowid

def get_total_items(cursor):
    global total_items
    cursor.execute('SELECT COUNT(*) FROM storage WHERE TYPE = "ITEM";')
    total_items = cursor.fetchone()[0]
    return total_items

def get_total_boxes(cursor):
    global total_boxes
    cursor.execute('SELECT COUNT(*) FROM storage WHERE TYPE = "BOX";')
    total_boxes = cursor.fetchone()[0]
    return total_boxes

def serialize_image_paths(image_paths):
    return json.dumps(image_paths)

def deserialize_image_paths(img_path_json):
    return json.loads(img_path_json)

def get_stats(cursor):
    stats = {
        'box_count': get_total_boxes(cursor),
        'item_count': get_total_items(cursor),
        'last_scan': 'N/A',
        'last_edit': 'N/A',
        'scanner': 'Connected'
    }
    return stats

def is_printer_connected(printer_name):
    """
    Check if the printer with the given name is connected.
    Works on both Windows and Unix-like systems.
    """
    try:
        if platform.system() == "Windows":
            # Use 'wmic' command to list printers on Windows
            result = subprocess.run(["wmic", "printer", "get", "name"], capture_output=True, text=True)
            printers = result.stdout.strip().splitlines()
        else:
            # Use 'lpstat' command on Unix-like systems (e.g., Linux, macOS)
            result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True)
            printers = [line.split()[1] for line in result.stdout.strip().splitlines() if "printer" in line]

        # Check if the printer name is in the list of available printers
        return printer_name in printers

    except Exception as e:
        print(f"Error while checking printer status: {e}")
        return False