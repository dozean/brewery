import csv
import codecs
import cStringIO
import base

# Soft requirement - graceful fail
try:
    import sqlalchemy

    # (sql type, storage type, analytical type)
    _sql_to_brewery_types = (
        (sqlalchemy.types.UnicodeText, "text",    "typeless"),
        (sqlalchemy.types.Text,        "text",    "typeless"),
        (sqlalchemy.types.Unicode,     "string",  "set"),
        (sqlalchemy.types.String,      "string",  "set"),
        (sqlalchemy.types.Integer,     "integer", "discrete"),
        (sqlalchemy.types.Numeric,     "float",   "range"),
        (sqlalchemy.types.DateTime,    "date",    "typeless"),
        (sqlalchemy.types.Date,        "date",    "typeless"),
        (sqlalchemy.types.Time,        "unknown", "typeless"),
        (sqlalchemy.types.Interval,    "unknown", "typeless"),
        (sqlalchemy.types.Boolean,     "boolean", "flag"),
        (sqlalchemy.types.Binary,      "unknown", "typeless")
    )

    _brewery_to_sql_type = {
        "string": sqlalchemy.types.Unicode,
        "text": sqlalchemy.types.UnicodeText,
        "date": sqlalchemy.types.Date,
        "time": sqlalchemy.types.DateTime,
        "integer": sqlalchemy.types.Integer,
        "numeric": sqlalchemy.types.Numeric,
        "boolean": sqlalchemy.types.SmallInteger
    }
except:
    _sql_to_brewery_types = []
    _brewery_to_sql_type = {}

def split_table_schema(table_name):
    """Get schema and table name from table reference.

    Returns: Tuple in form (schema, table)
    """

    split = table_name.split('.')
    if len(split) > 1:
        return (split[0], split[1])
    else:
        return (None, split[0])

class SQLDataStore(object):
    def __init__(self, url = None, connection = None, schema = None, **options):
        if connection:
            self.connection = connection
            self.engine = self.connection.engine
            self.close_connection = True
        else:
            self.engine = sqlalchemy.create_engine(url, **options)
            self.connection = self.engine.connect()
            self.close_connection = True
        
        self.metadata = sqlalchemy.MetaData()
        self.metadata.bind = self.engine
        self.metadata.reflect()
        self.schema = schema

    def close(self):
        if self.close_connection:
            self.connection.close()

    def dataset(self, name):
        return SQLDataset(self._table(name))

    def has_dataset(self, name):
        table = self._table(name, autoload = False)
        return table.exists()

    def create_dataset(self, name, fields, replace = False):
        if self.has_dataset(name):
            if not replace:
                raise ValueError("Dataset '%s' already exists" % name)
            else:
                table = self._table(name, autoload = False)
                table.drop(checkfirst=False)

        table = self._table(name, autoload = False)

        for field in fields:
            if not issubclass(type(field), base.Field):
                raise ValueError("field %s is not subclass of brewery.Field" % (field))

            concrete_type = field.concrete_storage_type

            if not issubclass(concrete_type.__class__, sqlalchemy.types.TypeEngine):
                concrete_type = _brewery_to_sql_type.get(field.storage_type)
                if not concrete_type:
                    raise ValueError("unable to create column for field '%s' of type '%s'" % 
                                        (field.name, field.storage_type))

            col = sqlalchemy.schema.Column(field.name, concrete_type)
            table.append_column(col)

        table.create()

        dataset = SQLDataset(table)
        return dataset

    def _table(self, name, autoload = True):
        split = split_table_schema(name)
        schema = split[0]
        table_name = split[1]

        if not schema:
            schema = self.schema

        table = sqlalchemy.Table(table_name, self.metadata, autoload = autoload, schema = schema)
        return table

class SQLDataset(object):
    def __init__(self, table):
        super(SQLDataset, self).__init__()
        self.table = table
        self._fields = None
        
    @property
    def field_names(self):
        names = [column.name for column in self.table.columns]
        return names
        
    @property
    def fields(self):
        if self._fields:
            return self._fields

        fields = []
        for column in self.table.columns:
            field = base.Field(name = column.name)
            field.concrete_storage_type = column.type
            
            for conv in _sql_to_brewery_types:
                if issubclass(column.type.__class__, conv[0]):
                    field.storage_type = conv[1]
                    field.analytical_type = conv[2]
                    break
                    
            if not field.storage_type:
                field.storaget_tpye = "unknown"

            if not field.analytical_type:
                field.analytical_type = "unknown"
            
            fields.append(field)

        self._fields = fields

        return fields

class SQLDataSource(base.DataSource):
    """docstring for ClassName
    
    Some code taken from OKFN Swiss library.
    """
    def __init__(self, connection = None, url = None,
                    table = None, statement = None, schema = None, **options):
        """Creates a relational database data source stream.
        
        :Attributes:
            * url: SQLAlchemy URL - either this or connection should be specified
            * connection: SQLAlchemy database connection - either this or url should be specified
            * table: table name
            * statement: SQL statement to be used as a data source (not supported yet)
            * options: SQL alchemy connect() options
        
        Note: avoid auto-detection when you are reading from remote URL stream.
        
        """
        if not url and not connection:
            raise AttributeError("Either url or connection should be provided for SQL data source")

        if not table and not statement:
            raise AttributeError("Either table or statement should be provided for SQL data source")

        if statement:
            raise NotImplementedError("SQL source stream based on statement is not yet implemented")

        if not options:
            options = {}

        self.url = url
        self.connection = connection
        self.table_name = table
        self.statement = statement
        self.schema = schema
        self.options = options
        
        self._field_names = None
        self._fields = None
                
    def initialize(self):
        """Initialize source stream:
        """
        self.datastore = SQLDataStore(self.url, self.connection, self.schema, **self.options)
        self.dataset = self.datastore.dataset(self.table_name)

    def finalize(self):
        self.datastore.close()

    @property
    def field_names(self):
        if self._field_names:
            return self._field_names
        self._field_names = self.dataset.field_names
        return self._field_names
        
    @property
    def fields(self):
        if self._fields:
            return self._fields
        self._fields = self.dataset.fields
        return self._fields

    def read_fields(self):
        self._fields = self.dataset.fields
        return self._fields

    def rows(self):
        if not self.dataset:
            raise RuntimeError("Stream is not initialized")
        return self.dataset.table.select().execute()

    def records(self):
        if not self.dataset:
            raise RuntimeError("Stream is not initialized")
        fields = self.field_names
        for row in self.rows():
            record = dict(zip(fields, row))
            yield record
        
class SQLDataTarget(base.DataTarget):
    """docstring for ClassName
    
    Some code taken from OKFN Swiss library.
    """
    def __init__(self, connection = None, url = None,
                    table = None, schema = None, truncate = False, 
                    create = False, replace = False, **options):
        """Creates a relational database data target stream.
        
        :Attributes:
            * url: SQLAlchemy URL - either this or connection should be specified
            * connection: SQLAlchemy database connection - either this or url should be specified
            * table: table name
            * truncate: whether truncate table or not
            * create: whether create table on initialize() or not
            * replace: Set to True if creation should replace existing table or not, otherwise
              initialization will fail on attempt to create a table which already exists.
            * options: other SQLAlchemy connect() options
        
        Note: avoid auto-detection when you are reading from remote URL stream.
        
        """
        if not url and not connection:
            raise AttributeError("Either url or connection should be provided for SQL data source")

        if not table and not statement:
            raise AttributeError("Either table or statement should be provided for SQL data source")

        if not options:
            options = {}

        self.url = url
        self.connection = connection
        self.table_name = table
        self.schema = schema
        self.options = options
        self.replace = replace
        self.create = create
        self.truncate = truncate
        
        self._field_names = None
        self._fields = None
                
    def initialize(self):
        """Initialize source stream:
        """
        self.datastore = SQLDataStore(self.url, self.connection, self.schema, **self.options)

        if self.create:
            self.dataset = self.datastore.create_dataset(self.table_name, self.fields, self.replace)
        else:
            self.dataset = self.datastore.dataset(self.table_name)
            
        if self.truncate:
            self.dataset.table.delete()

        self._update_fields()
        self.insert_command = self.dataset.table.insert()
        

    def finalize(self):
        self.datastore.close()

    @property
    def field_names(self):
        if self._field_names:
            return self._field_names
        if self._fields:
            return [field.name for field in self._fields]
        self._field_names = self.dataset.field_names
        return self._field_names
        
    @property
    def __get_fields(self):
        if self._fields:
            return self._fields
        self._fields = self.dataset.fields
        return self._fields

    def _update_fields(self):
        self._fields = self.dataset.fields
        self._field_names = [field.name for field in self._fields]
        
    def append(self, obj):
        if type(obj) == dict:
            record = obj
        else:
            record = dict(zip(self.field_names, obj))

        self.insert_command.execute(record)
