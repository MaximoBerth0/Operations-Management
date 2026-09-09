INVENTORY_PERMISSIONS = [
    # products
    "product:view",
    "product:create",
    "product:update",
    "product:activate",
    "product:deactivate",
    # categories
    "category:create",  # also gates adding a product to a category
    "category:delete",  # delete category
    "category:remove",  # remove a PRODUCT from category
    # stock
    "stock:create",
    "stock:in",
    "stock:out",
    "stock:adjust",
    "stock:view",
    # location
    "location:list",
    "location:view",
    "location:create",
    "location:update",
    "location:delete",
]
