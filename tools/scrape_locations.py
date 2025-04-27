import requests
from bs4 import BeautifulSoup
import json
import time


def scrape_space_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad status codes
        soup = BeautifulSoup(response.text, "html.parser")

        space_data = {}

        # --- Extract Title ---
        title_element = soup.find("h1", class_="page-header__title")
        space_name = (
            title_element.get_text(strip=True) if title_element else "Unknown Space"
        )

        # --- Find Infobox ---
        infobox = soup.find("aside", class_="portable-infobox")
        if not infobox:
            print(f"Warning: Infobox not found for {url}")

        # --- Extract from Infobox ---
        if infobox:
            # Extract Map & Type from the table within the section
            map_type_section = infobox.find("section", class_="pi-group")
            if map_type_section:
                map_cell = map_type_section.find("td", {"data-source": "map"})
                if map_cell and map_cell.find("a"):
                    map_value = map_cell.find("a").get_text(strip=True)
                    space_data["map"] = map_value.replace(" ", "_").upper()

                type_cell = map_type_section.find("td", {"data-source": "type"})
                if type_cell and type_cell.find("a"):
                    type_value = type_cell.find("a").get_text(strip=True)
                    space_data["location_type"] = type_value.upper()

            # Extract Connections and Path Types from the connections div
            connections_element = infobox.find("div", {"data-source": "connections"})
            connections = []
            ship_paths = []
            train_paths = []
            # Add other path types if needed (e.g., uncharted_paths = [])
            if connections_element:
                value_div = connections_element.find("div", class_="pi-data-value")
                if value_div:
                    links = value_div.find_all("a")
                    for link in links:
                        location_name = link.get_text(strip=True)
                        if not location_name:
                            continue
                        connections.append(location_name)

                        # Find the preceding image tag's span to determine path type
                        img_span = link.find_previous_sibling(
                            "span", {"typeof": "mw:File"}
                        )
                        if img_span:
                            img = img_span.find("img")
                            if img:
                                alt_text = img.get("alt", "").lower()
                                if "ship path" in alt_text:
                                    ship_paths.append(location_name)
                                elif (
                                    "train path" in alt_text
                                ):  # Adjust if alt text is different
                                    train_paths.append(location_name)
                                # Add elif for 'uncharted path', etc.

            space_data["connections"] = sorted(list(set(connections)))
            space_data["ship_paths"] = sorted(list(set(ship_paths)))
            space_data["train_paths"] = sorted(list(set(train_paths)))

            # Extract Gate
            gate_element = infobox.find("div", {"data-source": "gate"})
            if gate_element:
                value_div = gate_element.find("div", class_="pi-data-value")
                if value_div:
                    gate_value = value_div.get_text(strip=True)
                    # Check for specific gate colors if they exist as links/images
                    # assume text like "None" or a color name
                    space_data["gate_type"] = (
                        gate_value.upper() if gate_value.lower() != "none" else "NONE"
                    )

            # Extract Real World Location (using 'realworld')
            rwl_element = infobox.find("div", {"data-source": "realworld"})
            if rwl_element:
                value_div = rwl_element.find("div", class_="pi-data-value")
                if value_div:
                    space_data["real_world_location"] = value_div.get_text(strip=True)

        # --- Extract Expansion (from categories/breadcrumbs) ---
        expansion = "UNKNOWN"  # Default
        categories_div = soup.find("div", class_="page-header__categories")
        if categories_div:
            links = categories_div.find_all("a")
            for link in links:
                text = link.get_text(strip=True)
                if text == "Core Game":
                    expansion = "CORE"
                    break
                # Add elif for other expansions like "Forsaken Lore", "Mountains of Madness", etc.
                # elif text == "Forsaken Lore":
                #     expansion = "FORSAKEN_LORE" # Example
                #     break
        space_data["expansion"] = expansion

        # --- Extract Description (first paragraph after infobox/intro) ---
        description = "No description found."
        # Find the main content area (often mw-parser-output)
        content_body = soup.find("div", class_="mw-parser-output")
        if content_body:
            # Find the first paragraph <p> tag within the content body
            # This might need refinement if the first <p> isn't the description
            first_p = content_body.find("p")
            if first_p:
                # Clean up potential citation links like [1]
                for sup in first_p.find_all("sup"):
                    sup.decompose()
                description = first_p.get_text(strip=True)
                # Sometimes the first paragraph is just boilerplate, check length?
                if len(description) < 20:  # Arbitrary short length check
                    next_p = first_p.find_next_sibling("p")
                    if next_p:
                        for sup in next_p.find_all("sup"):
                            sup.decompose()
                        description = next_p.get_text(strip=True)

        space_data["description"] = description

        # --- Ensure all required keys exist with default values ---
        defaults = {
            "description": "Default description",
            "connections": [],
            "location_type": "UNKNOWN",
            "train_paths": [],
            "ship_paths": [],
            "gate_type": "NONE",
            "real_world_location": None,
            "expansion": "UNKNOWN",
            "map": "UNKNOWN",
        }
        for key, default_value in defaults.items():
            if key not in space_data:
                # Special handling for empty strings that should be None
                if key == "real_world_location" and space_data.get(key) == "":
                    space_data[key] = None
                elif key not in space_data:
                    space_data[key] = default_value

        return space_name, space_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None, None
    except Exception as e:
        print(f"Error parsing {url}: {e}")
        # You might want to print the traceback for debugging
        # import traceback
        # traceback.print_exc()
        return None, None


# --- Main Execution ---
space_urls = [
    "https://eldritchhorror.fandom.com/wiki/Space_1",
    "https://eldritchhorror.fandom.com/wiki/Space_2",
    "https://eldritchhorror.fandom.com/wiki/Space_3",
    "https://eldritchhorror.fandom.com/wiki/Space_4",
    "https://eldritchhorror.fandom.com/wiki/Space_5",
    "https://eldritchhorror.fandom.com/wiki/Space_6",
    "https://eldritchhorror.fandom.com/wiki/Space_7",
    "https://eldritchhorror.fandom.com/wiki/Space_8",
    "https://eldritchhorror.fandom.com/wiki/Space_9",
    "https://eldritchhorror.fandom.com/wiki/Space_10",
    "https://eldritchhorror.fandom.com/wiki/Space_11",
    "https://eldritchhorror.fandom.com/wiki/Space_12",
    "https://eldritchhorror.fandom.com/wiki/Space_13",
    "https://eldritchhorror.fandom.com/wiki/Space_14",
    "https://eldritchhorror.fandom.com/wiki/Space_15",
    "https://eldritchhorror.fandom.com/wiki/Space_16",
    "https://eldritchhorror.fandom.com/wiki/Space_17",
    "https://eldritchhorror.fandom.com/wiki/Space_18",
    "https://eldritchhorror.fandom.com/wiki/Space_19",
    "https://eldritchhorror.fandom.com/wiki/Space_20",
    "https://eldritchhorror.fandom.com/wiki/Space_21",
    "https://eldritchhorror.fandom.com/wiki/London",
    "https://eldritchhorror.fandom.com/wiki/Rome",
    "https://eldritchhorror.fandom.com/wiki/Istanbul",
    "https://eldritchhorror.fandom.com/wiki/Pyramids",
    "https://eldritchhorror.fandom.com/wiki/The_Heart_of_Africa",
    "https://eldritchhorror.fandom.com/wiki/Arkham",
    "https://eldritchhorror.fandom.com/wiki/Buenos_Aires",
    "https://eldritchhorror.fandom.com/wiki/San_Francisco",
    "https://eldritchhorror.fandom.com/wiki/Shanghai",
    "https://eldritchhorror.fandom.com/wiki/Tokyo",
    "https://eldritchhorror.fandom.com/wiki/Sydney",
    "https://eldritchhorror.fandom.com/wiki/The_Amazon",
    "https://eldritchhorror.fandom.com/wiki/The_Himalayas",
    "https://eldritchhorror.fandom.com/wiki/Tunguska",
]

all_spaces_data = {}
for url in space_urls:
    print(f"Scraping {url}...")
    name, data = scrape_space_page(url)
    if name and data:
        all_spaces_data[name] = data
    else:
        print(f"Failed to scrape data for {url}")
    time.sleep(0.5)  # Be polite to the server, wait half a second

# Save to JSON file
output_filename = "eldritch_horror_locations.json"  # Renamed to be more general
with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(all_spaces_data, f, indent=2, ensure_ascii=False)

print(f"\nData saved to {output_filename}")
