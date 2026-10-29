- **Three new modules read JSON, merge into a JSON file that another program owns, and write a
  private file: `jsonio`, `ownedjson` and `fsutil`.** `jsonio.loads` and `jsonio.load` refuse,
  with the line, what Python's `json` accepts and another program reads otherwise: a key twice in
  one object, `NaN`, `Infinity`, a number that overflows and a nesting deeper than 200; they also
  refuse an empty text, a byte order mark and a top level that is not an object.
  `ownedjson.merge` changes only the values that a change sets and keeps every other byte of the
  file, a minified layout and CRLF line ends too, and refuses a file that it cannot keep.
  `fsutil.write_private` creates the file with its mode before the first byte is written, so a
  token file is never readable under the umask's mode. Each module has its cases in
  `harness test`; no caller uses them yet.
