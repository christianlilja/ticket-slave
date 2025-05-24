"""
File handling utilities.

This module provides helper functions and constants related to file operations,
such as validating file extensions for uploads.
"""

# A set of allowed file extensions for uploads.
# Using a set provides efficient membership testing (e.g., `ext in ALLOWED_EXTENSIONS`).
# Extensions are stored in lowercase to ensure case-insensitive comparison.
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx', 'pptx', 'txt', 'log', 'csv', 'zip', 'rar'}
# Added 'gif', 'xlsx', 'pptx', 'log', 'csv', 'zip', 'rar' for broader common use cases.
# Consider making this configurable via application settings if more flexibility is needed.

def allowed_file(filename):
    """
    Checks if a given filename has an extension that is in the set of
    `ALLOWED_EXTENSIONS`.

    The check is case-insensitive.

    Args:
        filename (str): The name of the file to check (e.g., "document.pdf", "image.JPG").

    Returns:
        bool: True if the filename has an allowed extension, False otherwise.
              Returns False if the filename does not contain a '.' (i.e., no apparent extension).
    
    Example:
        allowed_file("my_image.png")  # True
        allowed_file("archive.ZIP")   # True
        allowed_file("script.py")     # False (if 'py' is not in ALLOWED_EXTENSIONS)
        allowed_file("nodotfilename") # False
    """
    # 1. Check if a '.' character exists in the filename, indicating an extension part.
    # 2. If it exists, split the filename at the last '.' to get the extension.
    #    `rsplit('.', 1)` splits from the right, at most once. `[1]` gets the part after the dot.
    # 3. Convert the extracted extension to lowercase for case-insensitive comparison.
    # 4. Check if this lowercase extension is present in the `ALLOWED_EXTENSIONS` set.
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
