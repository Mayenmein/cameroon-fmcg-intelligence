"""Saves constants used in the project."""
PRODUCT_CATEGORIES = {
    "fish_mackerel":          "protein",
    "meat_beef":              "protein",
    "oil":                    "oil",
    "rice":                   "staple",
    "maize":                  "staple",
    "wheat_flour":            "staple",
    "bananas":                "fruit",
    "cassava":                "root",
    "cocoyam_fao":            "root",
    "sorghum":                "cereal",
    "beans_fao":              "legume",
    "potatoes_fao":           "root",
    "plantains_fao":          "fruit",
}

DROP_FAO_DUPLICATES = {
    "cassava_fao", "maize_fao", "rice_fao", "wheat_flour_fao",
}

# Non-product rows to exclude entirely.
EXCLUDE = {"food_price_index", "exchange_rate_unofficial"}

TRADE_PRODUCT_MAP = {
    "rice":         "rice",
    "maize":        "maize",
    "wheat":        "wheat_flour",
    "edible_oils":  "oil",
}

REGION_WEIGHTS = {
        1: 0.22,   # Centre (Yaoundé)
        2: 0.20,   # Littoral (Douala)
        3: 0.10,   # West
        4: 0.09,   # Far North
        5: 0.08,   # North
        6: 0.08,   # Northwest
        7: 0.07,   # Southwest
        8: 0.06,   # Adamawa
        9: 0.05,   # East
        10: 0.05,  # South
    }