# OGR 2 BigQuery JSON

Convert files with simple features data (Shape, GeoJSON, etc) to newline delimited JSON files that can be imported into BigQuery. Schema files are also generated that can be used to create BigQuery tables programmatically or through the BigQuery Console.

The program uses the GDAL library to convert the source file to a [GeoJSONSeq](https://gdal.org/drivers/vector/geojsonseq.html) file, and then uses it to create the newline delimited JSON file. The GeoJSONSeq file is deleted afterward, unless the &#x2011;k / &#x2011;&#x2011;keep_geojsonseq option is used.

## Warning
**This was intended/started as a coding exercise, and is not production-ready code. There is very little error handling or checking if you are about to do something really bad! Use at your own risk!**

## Table of Contents

- [OGR 2 BigQuery JSON](#ogr-2-bigquery-json)
  - [Warning](#warning)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Usage](#usage)
    - [Positional arguments:](#positional-arguments)
    - [Options](#options)
    - [Examples](#examples)
  - [Output Files](#output-files)
  - [Tips / Troubleshooting](#tips--troubleshooting)
    - [Duplicate vertex errors when importing into BigQuery](#duplicate-vertex-errors-when-importing-into-bigquery)
    - [Error creating temporary GeoJSONSeq file](#error-creating-temporary-geojsonseq-file)
  - [TODO](#todo)

## Prerequisites

- Python 3.10.x (this was developed with Python 3.10.12, but an earlier version may work).
- [GDAL](https://gdal.org) installed on your system
  - On Ubuntu 22.04.03, the following installed all necessary packages: `sudo apt install gdal-bin libgdal-dev python3-gdal`.
- Python bindings for your version of GDAL, which ideally would be what `pip install GDAL` installs by default. However, I needed an earlier/specific version to match my native GDAL library (3.4.1, the version specified in requirements.txt). Try this if pip is giving errors when installing GDAL: `pip install GDAL=="$(gdal-config --version).*"` See the [*pip* section of the GDAL documentation](https://gdal.org/api/python_bindings.html#pip).

## Usage

**ogr2bqjson.py** *[-h] [-f] [-k] [-p] [-s] [-c COLUMNS] [-d OUTPUT_DIRECTORY] [-e EXTENSION] [-o OUTPUT_FILEPATH] [-v CONVERT_OPTIONS]* **source**

### Positional arguments:

| Name | Description |
| ----------- | ----------- |
| source | Path to the source file or directory to convert. |

*Note: positional arguments can be placed at the very beginning or very end, and the order of the options do not matter. Both of the following examples are valid and will do the same thing:*
```
python ogr2bqjson.py -k -p -o /output_dir/baz.json /source_dir/foo.bar
```
```
python ogr2bqjson.py /source_dir/foo.bar -p -o /output_dir/baz.json -k
```


### Options

| Option | Description |
| ----------- | ----------- |
| -h, &#x2011;&#x2011;help | Show help message and exit. |
| -f, &#x2011;&#x2011;force_overwrite | Overwrite files if they already exist, otherwise an underscore and number ("_n") will be appended to the output file's name: duplicate_01.json, duplicate_02.json, etc. |
| -k, &#x2011;&#x2011;keep_geojsonseq | Do not delete the GeoJSONSeq files created when a source file is not [GeoJSONSeq](https://gdal.org/drivers/vector/geojsonseq.html) with a WGS84 reference system. |
| -p, &#x2011;&#x2011;create_parents | Make directories and parent directories for output files, if they don't already exist. |
| -s, &#x2011;&#x2011;skip_schemas | Skip generating schema files.|
| -c, &#x2011;&#x2011;columns | JSON string to limit or rename the columns for geographic data in the output's schema. Use a JSON array literal if you want to set which columns to include without changing their default names. Use a JSON object to set and/or rename columns. "geometry" refers to the column that will contain the geometry as a GEOGRAPHY datatype; "geojson" the column that will have a complete copy of a geo object as a GeoJSON formatted STRING; and "geojson_geometry" the column containing just the geometry object as a GeoJSON formatted STRING. Leaving out a column will result in it being excluded from the schema. Note: only the "geometry" column is included by default. The "geojson" and/or "geojson_geometry" columns can be added manually using this option. |
| -d, &#x2011;&#x2011;output_directory | The path to the directory to save converted files to. The files will be given the same basename as the source, but with .json as the extension. Ignored if the &#x2011;&#x2011;output_filepath option is present. |
| -e, &#x2011;&#x2011;extension | Extension of the files to convert when the source path is a directory. Cannot be used when the source path is a file. |
| -o, &#x2011;&#x2011;output_filepath | The full filepath to save the converted file to. If omitted the file will be saved with the same basename and location as the source, but with the .json extension. Cannot be used when the source path is a directory. |
| -v, &#x2011;&#x2011;convert_options | String containing options to pass to GDAL VectorTranslate() during conversion. These are the same options you would use with ogr2org2 on the cli (see https://gdal.org/programs/ogr2ogr.html or type "*ogr2ogr &#x2011;&#x2011;help*" on the command line). Cannot include any of the following inside the string: *-f, -of, -t_srs*. An equals sign is required before the string if any part of the string contains a hyphen. |

### Examples

**Convert a file (no options).** *Output files will be saved to the same directory, using the same basename as the source. In this case: /source_dir/foo.json*
```
python ogr2bqjson.py /source_dir/foo.bar
```

**Save to a different directory.**
```
python ogr2bqjson.py -d /output_dir /source_dir/foo.bar
```

**Save with a different basename**
```
python ogr2bqjson.py -o /source_dir/baz.json /source_dir/foo.bar
```

**Convert all files with the .shp extension.** *The `-e` option is required, but the `-d` option is not. A trailing `/` in the source or destination directories are not required either.*
```
python ogr2bqjson.py /source_dir/ -e shp -d /output_dir
```

**Limit and/or rename the *properties* attributes in the schema.** *The `=` after `-v` is required if any part of the string contains a hyphen.*
```
python ogr2bqjson.py -v='-sql "SELECT attr1, attr2 AS qux FROM foo"' /source_dir/foo.bar
```

**Rename the *geometry* column in the schema.**
```
python ogr2bqjson.py -c "{\"geometry\":\"coordinates\"}" /source_dir/foo.bar
```

**Only include the *geojson_geometry* column in the schema.**
```
python ogr2bqjson.py -c "[\"geojson_geometry\"]" /source_dir/foo.bar
```

**Include all geo columns in the schema.**
```
python ogr2bqjson.py -c "[\"geometry\",\"geojson\",\"geojson_geometry\"]" /source_dir/foo.bar
```


## Output Files

- **filename.json**: A file containing the geographic features, one per line, in newline delimited JSON (ndjson) format, that can be imported into a BigQuery table. The schema will consist of the following columns, unless the *&#x2011;&#x2011;convert_options* and/or *&#x2011;&#x2011;columns* flags are used to alter them:
  - **geometry**: The feature's geometry member as a GeoJSON WGS84 formatted string, intended to be imported as a *[GEOGRAPHY](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types#geography_type)* datatype.
  - **geojson**: The entire feature, including properties and geometry, as a GeoJSON WGS84 formatted string, intended to be imported as a *STRING* datatype. *Note: This column is excluded from the schema by default. Use the &#x2011;&#x2011;columns / &#x2011;c option to include it*.
  - **geojson_geometry**: The feature's geometry member as a GeoJSON WGS84 formatted string, intended to be imported as a *STRING* datatype. *Note: This column is excluded from the schema by default. Use the &#x2011;&#x2011;columns / &#x2011;c option to include it*.
  - One column for each item within the *properties* member of the features
- **filename_SCHEMA.json**: A file containing a json version of the schema that can be used to programmatically create a table in BigQuery. Use the *&#x2011;&#x2011;skip_schema* option to prevent this file from being created
- **filename_SCHEMA.txt**: A plaintext file that can be used to copy/paste the schema when using the BigQuery Console to create a table. Use the *&#x2011;&#x2011;skip_schema* option to prevent this file from being created
- **filename_GeoJSONSeq.geojson**: The GeoJSONSeq file temporalty created, and then deleted, during the conversion process. Use the *&#x2011;&#x2011;keep_geojsonseq* / *&#x2011;k* option to prevent this file from being deleted.

## Tips / Troubleshooting

### Duplicate vertex errors when importing into BigQuery
If you are not able to import the newline delimited JSON file into BigQuery because it complains that an edge has a duplicate vertex with another edge, try the following:

- use the *&#x2011;&#x2011;columns* / *&#x2011;c* option to include the  "geojson_geometry" column, and exclude the "geometry" column (by omitting it). It is your choice whether to include the "geojson" column.
```
python ogr2bqjson.py -c "[\"geojson_geometry\]" /source_dir/foo.bar
```
- Import into a new BigQuery table
- Add a column with the GEOGRAPHY datatype to the table's schema, called *geometry* (or whatever else you want)
- Use BigQuery's [ST_GEOGFROMGEOJSON()](https://cloud.google.com/bigquery/docs/reference/standard-sql/geography_functions#st_geogfromgeojson) function in a SQL query to populate the *geometry* column using values from the *geojson_geometry* column. Setting the function's *make_valid* parameter to *TRUE* will have it attempt to repair issues like duplicate vertices during the conversion.

```sql
UPDATE my_proj_id.my_ds.my_table SET geometry = ST_GEOGFROMGEOJSON(geojson_geometry, make_valid => TRUE) WHERE geometry IS NULL;
```

### Error creating temporary GeoJSONSeq file
The program uses GDAL to convert the source to a [GeoJSONSeq](https://gdal.org/drivers/vector/geojsonseq.html) file, and uses this file to create the newline delimited JSON file. If there are errors during the conversion, you can use GDAL's [ogr2ogr](https://gdal.org/programs/ogr2ogr.html) command to troubleshoot/generate it yourself, and then use the GeoJSONSeq file as the source to create the newline delimited JSON file.
```
ogr2ogr -f GeoJSONSeq -t_srs crs:84 /tmp/foo_GeoJSONSeq.geojson /source_dir/foo.bar

python ogr2bqjson.py -o /output_dir/foo.json /tmp/foo_GeoJSONSeq.geojson

del /tmp/foo_GeoJSONSeq.geojson
```

If you find that ogr2ogr requires an option to convert your source to the proper format, you can use the `-v` option in ogr2bqjson.py to include it during the conversion.

For example, if you find *ogr2ogr* needs the `-if` option to open the source using the correct format/driver (e.g. *ESRI Shapefile*), then you can do something like this:
```
python ogr2bqjson.py -v='-if "ESRI Shapefile"' /source_dir/foo.bar
```

## TODO

- [ ] Unit tests
- [ ] Fix/prevent duplicate vertex issue, and/or warn the user if there are any
- [ ] Instructions for loading into BigQuery
- [ ] Instructions for using in Looker Studio map visualizations
