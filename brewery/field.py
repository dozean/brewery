class Field(object):
    """Dataset field information
    
    Attributes:
        * name - field name
        * label - optional human readable field label
        * storage_type - Normalized data storage type. The data storage type is abstracted
        * concrete_storage_type - Data store/database dependent storage type - this is the real name of
            data type as used in a database where the fields comes from or where
            the field is going to be created (this might be null if unknown)
        * analytical_type
        * missing_values = Array of values that represent missing values in the dataset for given field
    """
    
    storage_types = ["unknown", "string", "text", "integer", "float", "boolean", "date"]
    analytical_types = ["default", "typeless", "flag", "discrete", "range", 
                        "set", "ordered_set"]

    default_analytical_type = {
                    "unknown": "typeless",
                    "string": "typeless",
                    "text": "typeless",
                    "integer": "discrete",
                    "float": "range",
                    "date": "typeless"
                }

    def __init__(self, name, label = None, storage_type = "unknown", analytical_type = None, 
                    concrete_storage_type = None):
        self.name = name
        self.label = label
        self.storage_type = storage_type
        self.analytical_type = analytical_type
        self.concrete_storage_type = concrete_storage_type
        self.missing_values = missing_values
