from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, RedirectResponse
import os
import json
import sqlite3
from datetime import datetime
from generateBarcode import get_barcodes  # Import the updated function
from printBarcode import print_label
import subprocess  # For printer checking
import platform  # To determine the operating system
import re

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

DB_PATH = 'storage.db'
UPLOAD_DIRECTORY = "static/images/"

# Global variables to keep track of the total number of boxes and items
total_boxes = 0
total_items = 0

# Global variable to keep track of the last scanned single item
last_single_item_id = None
last_action = None


def setup_database():
    global total_boxes, total_items

    # Create the database if it does not exist
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    # Create `id_tracker` table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS id_tracker (
                        id INTEGER PRIMARY KEY AUTOINCREMENT
                    );''')

    # Create `storage` table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS storage (
            FIND INTEGER PRIMARY KEY NOT NULL,
            NAME TEXT NOT NULL,
            TYPE TEXT NOT NULL,
            DESCRIPTION TEXT NULL,
            WEIGHT INTEGER NULL,
            BARCODE_NUMBER INTEGER NULL,
            BARCODE_IMG_PATH TEXT NULL,
            DATE_CREATED TEXT NOT NULL,
            DATE_MODIFIED TEXT NOT NULL,
            PARENT TEXT NULL,
            IMG_PATH TEXT NULL,
            COST REAL NULL
        );''')

    # Check if the root "box" entry exists; if not, add it
    cursor.execute('SELECT * FROM storage WHERE NAME = "rootdirectory";')
    if cursor.fetchone() is None:
        # Generate a unique ID for the root box
        root_id = get_unique_find(connection)

        # Get the current date and time
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Insert the root "box" entry
        cursor.execute('''INSERT INTO storage 
            (FIND, NAME, TYPE, DESCRIPTION, WEIGHT, BARCODE_NUMBER, BARCODE_IMG_PATH, DATE_CREATED, DATE_MODIFIED, PARENT, IMG_PATH)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);''',
                       (root_id, "rootdirectory", "BOX", None, None, None, None, current_date,
                        current_date, None, None)
                       )
        connection.commit()

    connection.close()


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
    printer_status = "Connected" if is_printer_connected("LP320 Printer") else "Not Connected"
    print(printer_status)
    stats = {
        'box_count': get_total_boxes(cursor),
        'item_count': get_total_items(cursor),
        'last_scan': 'N/A',
        'last_edit': 'N/A',
        'scanner': printer_status,
        'printer': printer_status,
        'last_scanned': last_single_item_id
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
            # Clean up the printer list by stripping whitespace and removing empty strings
            printers = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        else:
            # Use 'lpstat' command on Unix-like systems (e.g., Linux, macOS)
            result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True)
            printers = [line.split()[1].strip() for line in result.stdout.strip().splitlines() if "printer" in line]

        # Print out the cleaned list of printers
        #print(f"Printers found: {printers}")

        # Check if the printer name is in the list of available printers
        return printer_name in printers

    except Exception as e:
        print(f"Error while checking printer status: {e}")
        return False


def is_circular_dependency(connection, potential_parent_id, child_id):
    """
    Recursively checks if there is a circular dependency by seeing if the potential parent box is already inside the child box.
    """
    cursor = connection.cursor()
    # Start by checking if the potential parent ID is the same as the child ID or any of its ancestors
    cursor.execute('SELECT PARENT FROM storage WHERE FIND = ?', (child_id,))
    parent_id = cursor.fetchone()

    # If the item has no parent (root level), return False
    if not parent_id or not parent_id[0]:
        return False

    # If the potential parent is found in the current parent_id chain, circular dependency exists
    if parent_id[0] == potential_parent_id:
        return True

    # Recursively check the next level up
    return is_circular_dependency(connection, potential_parent_id, parent_id[0])


def get_unique_name(connection, base_name, base_id):
    print("unique name inputs: ", base_name, base_id)
    cursor = connection.cursor()
    cursor.execute('SELECT NAME, FIND FROM storage WHERE NAME LIKE ?', (f'{base_name}%',))
    existing_names = cursor.fetchall()

    # Print the existing names for debugging purposes
    print("Existing names:", existing_names)

    # If there are no matching names, return the base_name unchanged
    if not existing_names:
        print("returning original name")
        return base_name

    # Check if the stored_id matches the base_id and names are identical (case-insensitive)
    for name, stored_id in existing_names:
        if stored_id == base_id and name.lower() == base_name.lower():
            return base_name

    # Regular expression to match names in the format: name, name(1), name(2), etc.
    base_pattern = re.compile(rf'^{re.escape(base_name)}\((\d+)\)$')
    number_pattern = re.compile(r'^(.*?)(\((\d+)\))?$')

    # Check if the base_name already ends with a number in parentheses
    base_match = number_pattern.match(base_name)
    if base_match:
        base_name_without_number = base_match.group(1).strip()
        base_number = int(base_match.group(3)) if base_match.group(3) else 0
    else:
        base_name_without_number = base_name
        base_number = 0

    # Find all the numbers in the existing names
    existing_numbers = set()
    for loop_index, (name_tuple, name_id) in enumerate(existing_names, start=1):
        name = name_tuple
        match = base_pattern.search(name)

        # Print the loop number
        print(f"Loop number: {loop_index}")

        if match:
            # Print all captured groups for debugging purposes
            print("Match found:", match.group(0))  # Full match
            print("All groups:", match.groups())  # Prints all groups in a tuple

            if name_id != base_id:  # Ensure name_id is not equal to base_id
                number = int(match.group(1))  # Assuming the first group captures a number
                existing_numbers.add(number)

    # Find the smallest missing number starting from 1
    min_number = 1
    while min_number in existing_numbers:
        min_number += 1

    # Return the base_name without the old number, with the next smallest number appended
    return f"{base_name_without_number}({min_number})"


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, box_id: int = None):
    global total_boxes, total_items
    parent_data = None
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    # If no box_id is provided, use the rootdirectory
    if box_id is None:
        cursor.execute('SELECT * FROM storage WHERE FIND = 1;')
        root_box = cursor.fetchone()

        parent_data = {
            'id': root_box[0],
            'name': root_box[1],
            'type': root_box[2],
            'description': root_box[3],
            'weight': root_box[4],
            'barcode_num': root_box[5],
            'barcode_path': root_box[6],
            'date_created': root_box[7],
            'date_modified': root_box[8],
            'parent': root_box[9],
            'images': root_box[10],
            'cost': root_box[11]
        }

        if root_box is None:
            return HTMLResponse(content="Root directory not found.", status_code=404)

        box_id = root_box[0]  # The FIND value of the "rootdirectory"
        box_name = root_box[1]  # The name of the "rootdirectory"
    else:
        # Fetch the name of the box using the provided box_id
        cursor.execute('SELECT * FROM storage WHERE FIND = ?', (box_id,))
        result = cursor.fetchone()

        parent_data = {
            'id': result[0],
            'name': result[1],
            'type': result[2],
            'description': result[3],
            'weight': result[4],
            'barcode_num': result[5],
            'barcode_path': result[6],
            'date_created': result[7],
            'date_modified': result[8],
            'parent': result[9],
            'images': result[10],
            'cost': result[11]
        }

        if result is None:
            return HTMLResponse(content="Box not found.", status_code=404)

    cursor.execute('SELECT * FROM storage WHERE PARENT = ?', (box_id,))
    result = cursor.fetchall()

    child_data = [
        {
            'id': column[0],
            'name': column[1],
            'type': column[2],
            'description': column[3],
            'weight': column[4],
            'barcode_num': column[5],
            'barcode_path': column[6],
            'date_created': column[7],
            'date_modified': column[8],
            'parent': column[9],
            'images': column[10],
            'cost': column[11]
        } for column in result
    ]

    stats = get_stats(cursor)

    connection.close()

    # Return the updated template with box name and ID
    return templates.TemplateResponse('homepage.html', {
        'request': request,
        'stats': stats,
        'parent': parent_data,
        'data': child_data
    })


@app.get("/new/{item_type}", response_class=HTMLResponse)
async def new_item(request: Request, item_type: str):  # Ensure `item_type` is included here
    global total_boxes, total_items
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    stats = get_stats(cursor)

    connection.close()

    item_data = {
        'id': None,
        'name': None,
        'type': item_type,
        'description': None,
        'weight': None,
        'barcode_num': None,
        'barcode_path': None,
        'date_created': None,
        'date_modified': None,
        'parent': None,
        'images': None,
        'cost': None
    }

    return templates.TemplateResponse('add.html', {
        'request': request,
        'stats': stats,
        'data': item_data,
        'parent': item_data,
        'opp': 'ADD'
    })


@app.post("/add/{item_type}", response_class=HTMLResponse)
async def add_item(
    request: Request,
    item_type: str,
    name: str = Form(...),
    description: str = Form(...),
    weight: int = Form(...),
    parent: str = Form(None),
    cost: str = Form(...),
    images: list[UploadFile] = File([])  # Accept multiple image files
):
    try:
        '''
        print(f"Item Type: {item_type}")
        print(f"Name: {name}")
        print(f"Description: {description}")
        print(f"Weight: {weight}")
        print(f"Parent: {parent}")
        print(f"Cost: {cost}")
        print(f"Number of images received: {len(images)}")
        for i, image in enumerate(images):
            print(f"Image {i + 1}: Filename = {image.filename}, Content Type = {image.content_type}")
        '''

        if not parent:
            parent = 1
        else:
            parent = int(parent)  # Convert to integer if provided

        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        stats = get_stats(cursor)

        # Check if the parent ID exists and is of type 'BOX'
        cursor.execute('SELECT FIND, TYPE FROM storage WHERE FIND = ? AND TYPE = "BOX";', (parent,))
        parent_record = cursor.fetchone()

        print("Parent Record: ", parent_record)

        item_data = {
            'id': None,
            'name': name,
            'type': item_type,
            'description': description,
            'weight': weight,
            'barcode_num': None,
            'barcode_path': None,
            'date_created': None,
            'date_modified': None,
            'parent': None,
            'images': None,
            'cost': cost
        }

        if parent_record is None:
            error_message = f"Parent ID {parent} does not exist or is not of type 'BOX'."
            return templates.TemplateResponse('add.html', {
                'request': request,
                'stats': stats,
                'data': item_data,
                'parent': item_data,
                'opp': 'ADD',
                'error': error_message
            })

        image_paths = []
        if images:
            for image in images:
                # Check if the filename is not blank before proceeding
                if not image.filename.strip():
                    print("Empty filename detected, skipping this file.")
                    continue

                # Save each image to the UPLOAD_DIRECTORY
                image_path = os.path.join(UPLOAD_DIRECTORY, image.filename)
                with open(image_path, "wb") as buffer:
                    buffer.write(await image.read())
                image_paths.append(image_path)

        # Set img_path_json to None if no images are uploaded
        img_path_json = serialize_image_paths(image_paths) if image_paths else None

        # Generate a unique FIND value
        find = get_unique_find(connection)
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Ensure the name is unique
        name = get_unique_name(connection, name, find)

        # Generate a unique barcode using the FIND value and get its image path
        barcode_image_path, barcode_number = get_barcodes(find)
        print_label(barcode_image_path, "LP320 Printer")
        # Insert the new item or box into the storage table
        cursor.execute('''
            INSERT INTO storage 
            (FIND, NAME, TYPE, DESCRIPTION, WEIGHT, BARCODE_NUMBER, BARCODE_IMG_PATH, DATE_CREATED, DATE_MODIFIED, PARENT, IMG_PATH, COST) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (barcode_number, name, item_type, description, weight, barcode_number, barcode_image_path, current_date, current_date, parent, img_path_json, cost))

        #barcode_number is used for find to make it easier to search for boxes or items when scanning their barcode

        connection.commit()
        connection.close()

        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        print(f"Error while processing item: {e}")
        return HTMLResponse(content="Error while processing item.", status_code=500)


@app.get("/delete/{item_id}", response_class=HTMLResponse)
async def delete_item(request: Request, item_id: int):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute('UPDATE storage SET PARENT = 1 WHERE PARENT = ?', (item_id,))

        cursor.execute('DELETE FROM storage WHERE FIND = ?', (item_id,))
        cursor.execute('DELETE FROM id_tracker WHERE id = ?', (item_id,))

        # Commit the changes and close the connection
        connection.commit()
        connection.close()

        # Redirect to the homepage after deletion
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        print(f"Error while deleting item: {e}")
        return HTMLResponse(content="Error while deleting item.", status_code=500)


@app.get("/modify/{item_id}", response_class=HTMLResponse)
async def modify_item(request: Request, item_id: int):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Fetch the item details to be modified
        cursor.execute('SELECT * FROM storage WHERE FIND = ?', (item_id,))
        column = cursor.fetchone()

        if not column:
            return HTMLResponse(content="Item not found.", status_code=404)

        # Deserialize image paths from JSON if they exist
        image_paths = deserialize_image_paths(column[10]) if column[10] else []

        item_data = {
            'id': column[0],
            'name': column[1],
            'type': column[2],
            'description': column[3],
            'weight': column[4],
            'barcode_num': column[5],
            'barcode_path': column[6],
            'date_created': column[7],
            'date_modified': column[8],
            'parent': column[9],
            'images': image_paths,  # Use the deserialized list of image paths
            'cost': column[11]
        }

        stats = get_stats(cursor)
        connection.close()

        # Render the add.html template with item data for modification
        return templates.TemplateResponse('add.html', {
            'request': request,
            'stats': stats,
            'data': item_data,
            'parent': item_data,
            'opp': 'MODIFY'
        })

    except Exception as e:
        print(f"Error while fetching item for modification: {e}")
        return HTMLResponse(content="Error while fetching item for modification.", status_code=500)


@app.post("/modify/{item_id}", response_class=HTMLResponse)
async def modify_item_submit(
        request: Request,
        item_id: int,
        name: str = Form(...),
        description: str = Form(...),
        weight: int = Form(...),
        parent: int = Form(...),
        cost: str = Form(...),
        images: list[UploadFile] = File([]),  # Accept new images
        delete_images: list[str] = Form([])  # List of images marked for deletion
):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Fetch the current item details to modify images
        cursor.execute('SELECT IMG_PATH FROM storage WHERE FIND = ?', (item_id,))
        current_item = cursor.fetchone()

        print("starting unique name")
        # Ensure the name is unique
        name = get_unique_name(connection, name, item_id)
        print("modified name: ", name)

        if not current_item:
            return HTMLResponse(content="Item not found.", status_code=404)

        # Deserialize existing image paths
        existing_image_paths = deserialize_image_paths(current_item[0]) if current_item[0] else []

        # Remove images that are marked for deletion from the list
        updated_image_paths = [path for path in existing_image_paths if path not in delete_images]

        # Process new uploaded images and add their paths
        for image in images:
            # Check if the filename is not blank before proceeding
            if not image.filename.strip():
                print("Empty filename detected, skipping this file.")
                continue

            # Save each image to the UPLOAD_DIRECTORY
            image_path = os.path.join(UPLOAD_DIRECTORY, image.filename)
            with open(image_path, "wb") as buffer:
                buffer.write(await image.read())
            updated_image_paths.append(image_path)

        # Serialize updated image paths into JSON format
        img_path_json = serialize_image_paths(updated_image_paths)

        # Update the item in the database
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE storage
            SET NAME = ?, DESCRIPTION = ?, WEIGHT = ?, DATE_MODIFIED = ?, PARENT = ?, COST = ?, IMG_PATH = ?
            WHERE FIND = ?;
        ''', (name, description, weight, current_date, parent, cost, img_path_json, item_id))

        connection.commit()
        connection.close()

        # Redirect to the homepage after modification
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        print(f"Error while modifying item: {e}")
        return HTMLResponse(content="Error while modifying item.", status_code=500)


@app.get("/display-all", response_class=HTMLResponse)
async def homepage(request: Request, box_id: int = None):
    global total_boxes, total_items
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute('SELECT * FROM storage WHERE FIND = 1')
    root_box = cursor.fetchone()

    parent_data = {
        'id': root_box[0],
        'name': root_box[1],
        'type': root_box[2],
        'description': root_box[3],
        'weight': root_box[4],
        'barcode_num': root_box[5],
        'barcode_path': root_box[6],
        'date_created': root_box[7],
        'date_modified': root_box[8],
        'parent': root_box[9],
        'images': root_box[10],
        'cost': root_box[11]
    }

    # Fetch all items whose PARENT is the FIND of the current box
    cursor.execute('SELECT * FROM storage')
    item_list = cursor.fetchall()

    # Prepare the items data structure
    item_data = [
        {
            'id': column[0],
            'name': column[1],
            'type': column[2],
            'description': column[3],
            'weight': column[4],
            'barcode_num': column[5],
            'barcode_path': column[6],
            'date_created': column[7],
            'date_modified': column[8],
            'parent': column[9],
            'images': column[10],
            'cost': column[11]
        } for column in item_list
    ]

    stats = get_stats(cursor)

    connection.close()

    # Return the updated template with box name and ID
    return templates.TemplateResponse('display-all.html', {
        'request': request,
        'data': item_data,
        'stats': stats,
        'parent': parent_data
    })


@app.get("/reprint/{item_id}", response_class=HTMLResponse)
async def reprint_barcode(request: Request, item_id: int):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Fetch the barcode image path for the given item ID
        cursor.execute('SELECT * FROM storage WHERE FIND = ?', (item_id,))
        result = cursor.fetchone()

        if not result or not result[6]:
            connection.close()
            return HTMLResponse(content="Barcode image not found for the specified item.", status_code=404)

        item_data = {
            'id': result[0],
            'name': result[1],
            'type': result[2],
            'description': result[3],
            'weight': result[4],
            'barcode_num': result[5],
            'barcode_path': result[6],
            'date_created': result[7],
            'date_modified': result[8],
            'parent': result[9],
            'images': deserialize_image_paths(result[10]) if result[10] else None,
            'cost': result[11]
        }

        # Print the barcode image
        print_label(result[6], "LP320 Printer")

        stats = get_stats(cursor)

        connection.close()

        # Render the 'add.html' template to return to the current item view
        return templates.TemplateResponse('add.html', {
            'request': request,
            'stats': stats,
            'data': item_data,
            'parent': item_data,
            'opp': 'MODIFY'
        })

    except Exception as e:
        print(f"Error while reprinting barcode: {e}")
        return HTMLResponse(content="Error while reprinting barcode.", status_code=500)


@app.get("/search/{item_id}", response_class=HTMLResponse)
async def search_item(request: Request, item_id: str):
    global last_single_item_id
    try:
        # Remove leading zeros from the item_id
        stripped_item_id = item_id.lstrip('0')
        #print("stripped id: ", stripped_item_id)
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        stats = get_stats(cursor)
        scan_error = None
        search_error = None

        # Check if the item ID is numeric, indicating a barcode or ID search
        if stripped_item_id.isdigit():
            # Search for the item with the stripped ID or exact name in the storage table
            cursor.execute('SELECT * FROM storage WHERE FIND = ? OR NAME = ?', (stripped_item_id, item_id))
        else:
            # Search for items or boxes where the name contains the input
            cursor.execute('SELECT * FROM storage WHERE NAME LIKE ?', (f'%{item_id}%',))

        result = cursor.fetchall()

        item_data = []

        if not result:
            connection.close()
            print("Item/box not found.")
            search_error = f"{item_id} does not exist"
            return templates.TemplateResponse('homepage.html', {
                'request': request,
                'stats': stats,
                'data': item_data,
                'parent': item_data,
                'searchError': search_error
            })

        for column in result:
            # Deserialize image paths if they exist
            image_paths = deserialize_image_paths(column[10]) if len(column) > 10 and column[10] else []

            # Append the item data dictionary
            item_data.append({
                'id': column[0],
                'name': column[1],
                'type': column[2],
                'description': column[3],
                'weight': column[4],
                'barcode_num': column[5],
                'barcode_path': column[6],
                'date_created': column[7],
                'date_modified': column[8],
                'parent': column[9],
                'images': image_paths,
                'cost': column[11] if len(column) > 11 else None
            })

        # Handle the case where there is exactly one item in the search result
        if len(result) == 1:
            # Get the ID and type of the current single item found
            current_item_id = result[0][0]
            current_item_type = result[0][2]

            # Check if there is a previously tracked single item
            if last_single_item_id is not None:
                # Fetch the type of the newly scanned item to ensure it's a box
                cursor.execute('SELECT TYPE FROM storage WHERE FIND = ?', (current_item_id,))
                parent_type = cursor.fetchone()

                if parent_type and parent_type[0] == "BOX" and last_single_item_id != current_item_id:
                    # Update the parent of the previously tracked item
                    cursor.execute('''
                        UPDATE storage 
                        SET PARENT = ? 
                        WHERE FIND = ?;
                    ''', (current_item_id, last_single_item_id))
                    connection.commit()
                    # Clear the last_single_item_id after setting the parent
                    last_single_item_id = None
                else:
                    if not parent_type:
                        print("Error: Parent type is None.")
                        scan_error = "Error: Parent type is None."
                    elif parent_type[0] != "BOX":
                        print(f"Error: The new parent must be a 'BOX', but found '{parent_type[0]}'.")
                        scan_error = f"Error: The new parent must be a 'BOX', but found '{parent_type[0]}'."
                    elif last_single_item_id == current_item_id:
                        print("Error: The new parent is the same as the current item.")
                        scan_error = "Error: The new parent is the same as the current item."
                    last_single_item_id = None
            else:
                # Track the ID of the single item found
                last_single_item_id = current_item_id

        connection.close()

        # Render a template (e.g., 'homepage.html') to show the item details
        return templates.TemplateResponse('homepage.html', {
            'request': request,
            'stats': stats,
            'data': item_data,
            'parent': item_data,
            'headerError': scan_error
        })

    except Exception as e:
        print(f"Error while searching for item: {e}")
        return HTMLResponse(content="Error while searching for item.", status_code=500)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        setup_database()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9000)
