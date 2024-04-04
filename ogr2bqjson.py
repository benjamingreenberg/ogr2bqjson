import argparse
import json
import os
import sys
from typing import Tuple

import ndjson
from osgeo import gdal

reserved_convert_options = ['-f', '-of', '-t_srs']
default_column_names = ['geometry', 'geojson', 'geojson_geometry']


def main():
  parser = get_args_parser()
  args = parser.parse_args()
  arg_error = get_arg_errors(args)
  if arg_error:
    sys.exit(arg_error)

  if args.create_parents and (args.output_directory or args.output_filepath):
    if not create_missing_directories(
        args.output_filepath or args.output_directory,
        is_dir=(args.output_filepath is None)):
      # Error already printed to the console.
      sys.exit()

  columns = get_columns(args.columns)
  if columns is False:
    # Whatever the issue is, it was already printed to the console.
    sys.exit()
  if args.extension:
    convert_all(
      args.source,
      args.extension,
      columns=columns,
      convert_options=args.convert_options,
      do_keep_geojsonseq=args.keep_geojsonseq,
      output_directory=args.output_directory,
      skip_schemas=args.skip_schemas,
    )
  else:
    output_filepath = args.output_filepath
    if output_filepath:
      output_filepath = get_safe_filepath(
        output_filepath,
        args.force_overwrite,
        True)

    output_filepath, schema = convert_to_ndjson(
      args.source,
      can_overwrite=args.force_overwrite,
      columns=columns,
      convert_options=args.convert_options,
      do_keep_geojsonseq=args.keep_geojsonseq,
      output_directory=args.output_directory,
      output_filepath=output_filepath,
    )

    if not args.skip_schemas:
      path_root = os.path.splitext(output_filepath)[0]
      save_schema_files(schema, path_root, can_overwrite=args.force_overwrite)


def get_args_parser() -> argparse.ArgumentParser:
  """Initializes and configures parser

  Returns:
      argparse.ArgumentParser: The parser object
  """
  parser = argparse.ArgumentParser(
    description=(
      'Convert files with simple features data (shp, geojson, etc) to newline '
      'delimited JSON files that can be imported into BigQuery. Schema files '
      'are also generated that can be used to create BigQuery tables '
      'programmatically or through the BigQuery Console.'
    )
  )

  add_args_to_parser(parser)
  return parser


def add_args_to_parser(parser: argparse.ArgumentParser) -> None:
  """Add arguments to the parser.

  Args:
      parser (argparse.ArgumentParser): Parser to add arguments to.
  """
  parser.add_argument('source', help=(
    'Path to the source file or directory to convert. The --extension / -e '
    'option is required if the path is to a directory.'
  ))
  parser.add_argument('-f', '--force_overwrite', action='store_true', help=(
		'Overwrite files if they already exist, otherwise an underscore and number '
    '("_n") will be appended to the output file\'s name: duplicate_01.json, '
    'duplicate_02.json, etc.'
	))
  parser.add_argument('-k', '--keep_geojsonseq', action='store_true', help=(
		'Do not delete the GeoJSONSeq files created when a source file is not '
    'GeoJSONSeq with a WGS84 reference system. They will be saved with the same '
    'name and location as the json file, but end with _GeoJSONSeq.geojson. Note: '
    'the --force_overwrite / -f option is ignored for the GeoJSONSeq file. It '
    'will never overwrite an existing file, and will be given a unique name.'
	))
  parser.add_argument(
    '-c',
    '--columns',
    default='{"geometry":"geometry"}',
    help=(
      'JSON string to limit or rename the columns for geographic data in the '
      'output\'s schema. Use a JSON array literal if you want to set which '
      'columns to include without changing their default names. Use a JSON '
      'object to set and/or rename columns. "geometry" refers to the '
      'column that will contain the geometry as a GEOGRAPHY datatype; "geojson" '
      'the column that will have a complete copy of a geo object as a GeoJSON '
      'formatted STRING; and "geojson_geometry" the column containing just the '
      'geometry object as a GeoJSON formatted STRING. Leaving out a column will '
      'result in it being excluded from the schema. Note: only the "geometry" '
      'column is included by default. The "geojson" and/or "geojson_geometry" '
      'columns can be added manually using this option. See '
      '--convert_options / -v for info about limiting or renaming the '
      '"properties" columns. Examples: '
      'Include all columns: -c "[\\"geometry\\",\\"geojson\\"\\"geojson_geometry\\"] '
      'Rename geometry column: -c "{\\"geometry\\":\\"coordinates\\"}"'
    )
  )
  parser.add_argument('-d', '--output_directory', help=(
		'The path to the directory to save converted files to. The files will be '
    'given the same basename as the source, but with .json as the extension. '
    'Ignored if the --output_filepath option is present.'
	))
  parser.add_argument('-e', '--extension', help=(
		'Extension of the files to convert when the source path is a directory. '
    'Cannot be used when the source path is a file. Example: --extension shp'
	))
  parser.add_argument('-o', '--output_filepath', help=(
		'The full filepath to save the converted file to. If omitted the file will '
    'be saved with the same basename and location as the source, but with the '
    '.json extension. Cannot be used when the source path is a directory. Use '
    ' the --output_directory / -d option to save the file with the same '
    ' basename as the source, but to a different directory.'
	))
  parser.add_argument('-p', '--create_parents', action='store_true', help=(
		'Make directories and parent directories for output files, if they don\'t '
    'already exist.'
	))
  parser.add_argument('-s', '--skip_schemas', action='store_true', help=(
		'Skip generating schema files.'
	))
  parser.add_argument('-v', '--convert_options', default='', help=(
    'String containing options to pass to GDAL VectorTranslate() during '
    ' conversion. These are the same options you would use with ogr2org2 on the '
    'cli (see https://gdal.org/programs/ogr2ogr.html or type "ogr2ogr --help"). '
    'Cannot include the following options: '
    f'{", ".join(reserved_convert_options)}. For example, to change the '
    'column names of feature properties (equals sign is necessary):'
    '-v=\'-sql "SELECT attr1 AS foo, attr2 AS bar FROM source_basename"\''
  ))


def get_arg_errors(args: argparse.Namespace) -> str | None:
  """Find problems with argument values and return their description.

  Args:
      args (argparse.Namespace): The arguments to check

  Returns:
      str | None: The description of the first problem encountered, if any.
  """
  source_errors = get_source_errors(args.source, args.extension is not None)
  if source_errors:
    return source_errors

  if args.convert_options:
    for option in reserved_convert_options:
      if option in args.convert_options:
        return (f'Invalid Option: "{option}" is reserved and cannot be used '
                'within --convert_options / -v')

  if (args.output_directory
      and not is_output_directory_safe(args.output_directory, args.create_parents)):
    return (f'Invalid Output Path: "{ args.output_directory }" does not exist. '
            'Use the --create_parents option to create missing directories and '
            'their parents during execution.')

  output_file_path_errors = get_output_file_args_errors(
    args.output_filepath,
    args.force_overwrite,
    args.create_parents
  )
  if output_file_path_errors:
    return output_file_path_errors


def get_source_errors(source_path: str, should_be_dir: bool | None = False) -> str | None:
  """Find problems with the source path and return their description.

  Args:
      source_path (str): Path to the source file or directory
      should_be_dir (bool | None, optional): Whether the source should be a
        directory. Defaults to False.

  Returns:
      str | None: The description of the first problem encountered, if any.
  """
  if not source_path:
    return 'Invalid Source: source cannot be an empty string.'

  if not os.path.exists(source_path):
    return f'Invalid Source: "{ source_path }" does not exist.'

  if should_be_dir:
    if os.path.isfile(source_path):
      return ('Invalid Option: The --extension / -e option cannot be used when '
              'the source path is to a file.')
  else:
    if os.path.isdir(source_path):
      return ('Missing Option: --extension / -e is required when the source '
              'path is to a directory.')
    elif not is_supported_geofile(source_path):
      return (f'Invalid Source: "{ source_path }" is not recognized as a '
              'supported geofile format by gdal.')


def get_path_parts(path: str) -> dict:
  """Parse a path into its constituent parts.

  The dictionary will have the following keys:
    extension: Everything from the last dot of the path's filename to the end,
      or an empty string.
    filename_root: Everything between the last forward slash and last dot.
      Empty string if path ends in a forward slash.
    full_path: The same value passed to the function
    path_root: The full path stripped of its file extension, if there is one

  Args:
      path (str): The path to parse.

  Returns:
      dict: Dictionary keyed by the path parts.
  """
  path_root, extension = os.path.splitext(path)
  filename_root = os.path.splitext(os.path.basename(path))[0]
  source = {
    'extension': extension,
    'filename_root': filename_root,
    'full_path': path,
    'path_root': path_root,
  }
  return source


def is_supported_geofile(filepath: str) -> bool:
  """Determine if a file can be opened by gdal.

  Args:
      filepath (str): Path to the file

  Returns:
      bool: True if the file can be opened, False if can't be opened or missing.
  """
  try:
    gdal.UseExceptions()
    gdal.OpenEx(filepath)
    return True
  except Exception:
    return False


def is_output_directory_safe(
    dir_path: str,
    can_create_parents: bool | None = False) -> bool:
  """Determine whether it is ok to write to a directory.

    Note: This does not check the OS permissions on the directory.

  Args:
      dir_path (str): Path to the directory
      can_create_parents (bool | None, optional): Whether it is allowed to
        create missing directories or their parents. Defaults to False.

  Returns:
      bool: True if the directory exists or can_create_parents is True, otherwise False.
  """
  return can_create_parents or os.path.exists(dir_path)


def get_output_file_args_errors(output_filepath: str, can_overwrite: bool, can_create_parents:bool ) -> str | None:
  """Find problems with the output_filepath and return their description.

  Args:
      output_filepath (str): Value given for the output_filepath option
      can_overwrite (bool): If allowed to overwrite a file if it exists.
      can_create_parents (bool): Whether it is allowed to create missing
        directories or their parents.

  Returns:
      str | None: The description of the first problem encountered, if any.
  """
  if output_filepath:
    if is_output_file_safe(output_filepath, can_overwrite) is False:
      safe_file = get_safe_filepath(output_filepath)
      print (
        f'\nThe output file "{output_filepath}" already exists.\n'
        f'Do you want to save the converted file to "{safe_file}" instead?\n'
        'Note: use -f / --force_overwrite in the future to overwrite existing '
        'files automatically.'
      )
      do_exit = False
      while True:
        answer = input(
          '\nType "1" to use the new file, "2" to overwrite the existing file, '
          '"3" (or nothing) to exit, then press Enter:\n')
        if answer == '1':
            print(f'Will save output to {safe_file}')
            break
        elif answer == '2':
            print(f'Will overwrite {output_filepath}')
            break
        elif not answer or answer == '3':
            do_exit = True
            break

      if do_exit:
        return 'Exiting'
    elif not is_output_directory_safe(
        os.path.splitext(output_filepath)[0],
        can_create_parents):
      return (
        f'Invalid Output File: Cannot create "{output_filepath}" because '
        'its directory does not exists. Use the --create_parents option to '
        'create missing directories and their parents during execution.'
      )


def is_output_file_safe(filepath: str, can_overwrite: bool) -> bool:
  """Determine whether it is ok to write to a filepath.

    Note: This does not check the OS permissions on the file or directory.

  Args:
      filepath (str): Path to the file
      can_overwrite (bool): If allowed to overwrite the file if it exists.

  Returns:
      bool: True if file does not exist or can_overwrite is True, otherwise False.
  """
  return can_overwrite or not os.path.exists(filepath)


def create_missing_directories( path:str, is_dir:bool | None = False ) -> bool:
  """Create missing directories and parents for the given path.

  Args:
      path (str): The path whose directory and parents should be created.
      is_dir (bool | None, optional): Whether the path is a directory, rather
        a file. Defaults to False.

  Returns:
      bool: True if directories already exist or were successfully created,
        False if an error occurred.
  """
  try:
    if is_dir and not path.endswith('/'):
      path += '/'

    os.makedirs(
      os.path.dirname(path),
      exist_ok=True
    )
  except Exception as err:
    print('Error creating missing directories', str(err))
    return False

  return True


def get_columns( columns_args: str ) -> dict:
  """Determine geo columns to include based on the arg value, and return them.

  Args:
      columns_args (str): JSON containing the types and names of columns wanted.

  Returns:
      dict: Key / Value pair consisting of column type / column name.
  """
  if columns_args == '':
    print('--columns / -c contained an empty string. No geographic columns will '
          'be included in the schema.')
    return {}
  try:
    user_columns = json.loads(columns_args)
  except Exception as err:
    print('Invalid Columns: An error occurred when attempting to parse the '
          f'value for --columns / -c: "{err}". Make sure you entered valid JSON '
          'and have escaped quotation marks with a backslash ("value" should be '
          '\\"value\\")')
    return False

  columns = {}
  if not user_columns:
    print('--columns / -c contained an empty JSON object or array. No '
          'geographic columns will be included in the schema.')
  elif isinstance(user_columns, dict):
    columns = user_columns
  else:
    for column in user_columns:
      if column in default_column_names:
        columns[column] = column
      else:
        print(f'Unknown column "{column}".')
    if not columns:
      print( 'Invalid Columns: All column names given in --columns / -c were '
            f'invalid. Valid column names are: {", ".join(default_column_names)}. '
            'Unable to continue.')
      columns = False
  return columns


def convert_all(
    source_directory: str,
    target_extension: str,
    can_overwrite: bool | None = False,
    columns: dict | None = None,
    convert_options:str | None = None,
    do_keep_geojsonseq: bool | None = False,
    output_directory: dict | None = None,
    skip_schemas: bool | None = False, ) -> None:
  """Convert all files in a directory to newline delimited JSON.

  Args:
      source_directory (str): Path containing the files to convert
      target_extension (str): Extension of files to convert.
      can_overwrite (bool | None, optional): Whether to overwrite existing files.
        If not, a unique name will be chosen (see get_safe_filepath() for more
        info). Defaults to False.
      columns (dict | None, optional): The column(s) to place the geographic
        features in. See geojson_to_ndjson() for more info. Defaults to None.
      convert_options (str | None, optional): Options to pass to gdal. See
        convert_to_wgs84_geojsonseq() For more info. Defaults to None.
      do_keep_geojsonseq (bool | None, optional): Does not delete the temporary
        GeoJSONSeq files. Defaults to False.
      output_directory (str | None, optional): Path to the directory to save
        the converted files to. If omitted, the files will be saved in the
        source directory. Defaults to None.
      skip_schemas (bool, optional): Do not generate schema files. Defaults to False.
  """
  if not target_extension.startswith('.'):
    target_extension = '.' + target_extension

  if not source_directory.endswith('/'):
    source_directory += source_directory + '/'

  output_directory = output_directory or source_directory
  print((
    f'converting all {target_extension} files in {source_directory} and saving '
    f'them to {output_directory}...'
  ))
  for file in os.listdir(source_directory):
    if os.path.splitext(file)[1] == target_extension:
      full_filename = os.fsdecode(file)
      source_filepath = os.path.join(source_directory, full_filename)

      output_filepath, schema = convert_to_ndjson(
        source_filepath,
        columns=columns,
        convert_options=convert_options,
        output_directory=output_directory,
        can_overwrite=can_overwrite,
        do_keep_geojsonseq=do_keep_geojsonseq
      )

      if (not skip_schemas):
        path_root = os.path.splitext(output_filepath)[0]
        save_schema_files(schema, path_root, can_overwrite=can_overwrite)


def get_safe_filepath(
    initial_filepath:str,
    can_overwrite: bool | None = False,
    is_candidate: bool | None = True) -> str:
  """Find a filepath to write to starting with an initial filepath.

    If a file exists at the initial location, and it is not safe to overwrite
    it, or the initial filepath is not a candidate, then "_01" will be appended
    to the filename (foo/bar_01.json), and the filepath of the new candidate
    will be checked. The process repeats, incrementing the number by one, until
    a unique filepath is found: foo/bar_02.json, foo/bar_03.json, etc.

    Note: This does not check the OS permissions on the file or directory.

  Args:
      initial_filepath (str): The filepath to use a pattern.
      can_overwrite (bool | None, optional): Whether it is considered safe to
        overwrite existing files. Defaults to False.
      is_candidate (bool | None, optional): Whether the initial filepath should
        be evaluated. Defaults to True.

  Returns:
      str: The path to the file
  """
  path_root, extension = os.path.splitext(initial_filepath)
  i = 0
  if not is_candidate:
    i = 1
    initial_filepath = f'{path_root}_01{extension}'

  while not is_output_file_safe(initial_filepath, can_overwrite):
    i += 1
    initial_filepath = f'{path_root}_{i:02d}{extension}'

  return initial_filepath


def is_wgs84_geojsonseq(filepath: str) -> bool:
  """Determine if a file is encoded as GeoJSONSeq with a WGS84 reference system.

  It is recommended to check that the file exists and is a supported geographic
    features file before calling this function. There is no exception handling,
    by design, so that it isn't ambiguous whether a returned value is falsy
    because the file has a different encoding/reference system, or there was an
    error opening it.

  Args:
      filepath (str): Path to the file

  Returns:
      bool: True if the file is in the correct format, False if it is not.
  """
  gdal.UseExceptions()
  ds=gdal.OpenEx(filepath)

  return (ds.GetDriver().GetDescription() == 'GeoJSONSeq'
          and ds.GetLayer().GetSpatialRef().GetName() == 'WGS 84')


def geojson_to_ndjson(
    geojsonseq_filepath: str,
    output_filepath: str,
    columns: dict | None = {'geometry':'geometry','geojson':'geojson'}) -> dict:
  """Convert a GeoJSONSeq file to newline-delimited JSON

  Use convert_to_ndjson() instead of calling this directly, to ensure that the
  GeoJSONSeq file is in the correct format.

  Args:
      geojsonseq_filepath (str): Path to GeoJSONSeq file
      output_filepath (str): Path to save the nd JSON file
      columns (dict | None, optional): The column(s) to place the geographic
        features in. The value of the "geometry" key will be the name of the
        column for the feature's geometry member as a GEOGRAPHY datatype, and
        the value of the "geojson" key will be the name of the column with the
        entire feature, including properties and geometry, as a GeoJSON WGS84
        formatted STRING. Defaults to {'geometry':'geometry','geojson':'geojson'}.

  Returns:
      dict: Schema of the exported file
  """
  print((
    f'Converting GeoJSONSeq file at {geojsonseq_filepath} to ndjson and saving to '
    f'{output_filepath}...'
  ))
  rows = []
  schema = {}

  with open(geojsonseq_filepath, "r") as geojson_file:
    for line in geojson_file:
      row = {}
      line_item = ndjson.loads(line)[0]
      properties = line_item.get('properties', {})

      for key in properties:
        value = properties[key]
        row[key] = value
        schema[key] = get_column_type(value, schema.get(key))

      if 'geometry' in columns:
        row[columns['geometry']] = json.dumps(line_item['geometry'], ensure_ascii=False)
      if 'geojson' in columns:
        row[columns['geojson']] = json.dumps(line_item, ensure_ascii=False)
      if 'geojson_geometry' in columns:
        row[columns['geojson_geometry']] = json.dumps(line_item['geometry'], ensure_ascii=False)
      rows.append(row)

  if 'geometry' in columns:
      schema[columns['geometry']] = 'GEOGRAPHY'
  if 'geojson' in columns:
      schema[columns['geojson']] = 'STRING'
  if 'geojson_geometry' in columns:
      schema[columns['geojson_geometry']] = 'STRING'

  with open(output_filepath, 'w+') as json_file:
    ndjson.dump(rows, json_file)

  return schema


def get_column_type(
    value: str | int | float | bool,
    last_type: str | None = None) -> str:
  """Match a value's type to a BigQuery datatype.

  The last_type argument is for making sure the correct type for a column is
  found when using values from multiple rows. For example, if the value for a
  column in the first row is None, then the last_type for that column would be
  "UNKNOWN" until a row with an actual value in the column is reached. Another
  example is if the value for a column in the first row is an integer, then the
  last_type would be "INTEGER". But if in another row the column has a float,
  then the datatype for the column should be "FLOAT", since no precision/data
  is lost when inserting an integer into a float column.

  Args:
      value (str | int | float | bool): Value to match
      last_type (str | None, optional): Previous type detected for same
        kind/source of variable.

  Returns:
      str: A BigQuery datatype or UNKNOWN if it could not be determined.
  """
  column_type = 'UNKNOWN'
  if (value is None):
    column_type = 'UNKNOWN'
  if (isinstance(value, str)):
    column_type = 'STRING'
  elif (isinstance(value, int)):
    column_type = 'INTEGER'
  elif (isinstance(value, float)):
    column_type = 'FLOAT'
  elif (isinstance(value, bool)):
    column_type = 'BOOLEAN'

  if (last_type and last_type != column_type):
    if (last_type == 'STRING'):
      column_type = 'STRING'
    elif (last_type == 'FLOAT' and column_type == 'INTEGER'):
      column_type = 'FLOAT'

  return column_type


def convert_to_ndjson(
    input_filepath: str,
    can_overwrite: bool | None = False,
    columns: dict | None = None,
    convert_options:str | None = None,
    do_keep_geojsonseq: bool | None = False,
    output_directory: str | None = None,
    output_filepath: str | None = None) -> Tuple[str, dict]:
  """Convert to newline delimited JSON, return the output filepath and schema.

  If the input file is not encoded as GeoJSONSeq with a WGS84 reference system
  then a temporary file of that type will be created and used to convert to
  newline delimited JSON.

  Args:
      input_filepath (str): Path to features file
      can_overwrite (bool | None, optional): Whether to overwrite an existing
        file, if one exists. If False, a unique name will be chosen (see
        get_safe_filepath() for more info). Defaults to False.
      columns (dict | None, optional): The column(s) to place the geographic
        features in. See geojson_to_ndjson() for more info. Defaults to None.
      convert_options (str | None, optional): Options to pass to gdal. See
        convert_to_wgs84_geojsonseq() For more info. Defaults to None.
      do_keep_geojsonseq (bool | None, optional): Does not delete the
        intermediary GeoJSONSeq files. Defaults to False.
      output_directory (str | None, optional): Path to the directory to save
        the converted file to. If omitted, the file will be saved in the
        source directory. Defaults to None.
      output_filepath (str | None, optional): Path to save the converted file to.
        Defaults to None.

  Returns:
      Tuple[ str, dict ]: A Tuple containing a str of where the file was saved,
      and a dict of the schema.
  """
  if not output_filepath:
    output_filepath = get_output_filepath(
      input_filepath,
      '.json',
      can_overwrite=can_overwrite,
      output_directory=output_directory
    )

  schema = None
  temp_filepath = None
  if convert_options or not is_wgs84_geojsonseq( input_filepath ):
    temp_filepath = get_output_filepath(
      os.path.splitext(output_filepath)[0] + '_GeoJSONSeq',
      '.geojson',
      False,
      output_directory=output_directory
    )
    convert_to_wgs84_geojsonseq(input_filepath, temp_filepath, convert_options)
    input_filepath = temp_filepath

  schema = geojson_to_ndjson(input_filepath, output_filepath, columns=columns)
  if temp_filepath and not do_keep_geojsonseq:
    os.remove(temp_filepath)

  return output_filepath, schema


def get_output_filepath(
    source_filepath: str,
    extension: str,
    can_overwrite: bool | None = False,
    output_directory: str | None = None) -> str:
  """Build an output filepath using a source filepath and an extension.

  Args:
      source_filepath (str): Filepath to base the output filepath on.
      extension (str): Extension of the output filepath, including the dot.
      can_overwrite (bool | None, optional): Whether it is ok to overwrite an
        existing file. If False, a unique name will be chosen (see
        get_safe_filepath() for more info). Defaults to False.
      output_directory (str | None, optional): The directory for the output
        filepath, if different than the source. Defaults to None.

  Returns:
      str: Full path for the output file.
  """
  source = get_path_parts(source_filepath)
  output_directory = output_directory or os.path.dirname(source_filepath)
  filepath = os.path.join( output_directory, source['filename_root'] + extension )
  return get_safe_filepath(filepath, can_overwrite)


def convert_to_wgs84_geojsonseq(
    input_filepath: str,
    output_filepath: str,
    options:str | None = '') -> None:
  """Convert a geographic features file to a GeoJSON file

  Args:
      input_filepath (str): Path to the features file
      output_filepath (str): Path to save the GeoJSON file to.
      options (str | None, optional): String containing options to pass to gdal.
        This will be appended to "-f GeoJSONSeq -t_srs crs:84". Defaults to
        empty string.
  """
  print(f'Converting {input_filepath} to GeoJSONSeq and saving to {output_filepath}...')
  gdal.UseExceptions()
  ds = gdal.OpenEx(input_filepath)
  gdal.VectorTranslate(
    output_filepath,
    ds,
    options='-f GeoJSONSeq -t_srs crs:84 ' + options
  )
  ds = None


def save_schema_files(
    schema: dict,
    path_root: str,
    can_overwrite: bool | None = False) -> None:
  """Save the schema into json and plaintext files.

    The json version can be used to create a BigQuery table programmatically.
    The plaintext version can be used to copy/paste the schema when creating a
    table using the BigQuery Console.

  Args:
      schema (dict): Schema
      path_root (str): The directory path and basename to save the schemas to.
      can_overwrite (bool | None, optional): Whether to overwrite existing files.
        If not, a unique name will be chosen (see get_safe_filepath() for more
        info). Defaults to False.
  """
  json_filepath = get_safe_filepath(
    path_root  + '_SCHEMA.json',
    can_overwrite
  )
  print((
    f'Saving schema json file to {json_filepath}. You can use it when creating '
    'a BigQuery table programmatically.'
  ))
  with open(json_filepath, 'w+') as json_file:
    json.dump(schema, json_file)

  plaintext_filepath = get_safe_filepath(
    path_root  + '_SCHEMA.txt',
    can_overwrite
  )
  print((
    f'Saving plaintext schema file to {plaintext_filepath}. You can use it to '
    'copy/paste the schema when creating a table using the BigQuery Console.'
  ))
  schema_text = ''
  unknown_columns = []
  for key in schema.keys():
    schema_text += key + ":" + schema[key] + ",\n"
    if (schema[key] == 'UNKNOWN'):
      unknown_columns.append(key)

  # Remove trailing comma and newline
  schema_text = schema_text[:-2]
  with open(plaintext_filepath, 'w+') as text_file:
    text_file.write(schema_text)

  if len(unknown_columns) > 0:
    print((
      '\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!! WARNING !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n'
      'Schema has one or more columns whose values could not be determined:\n'
      f'\t\t{", ".join(unknown_columns)}\n'
      'Edit the schema files and enter the proper datatype(s) before using them'
    ))


if __name__ == '__main__':
  main()
