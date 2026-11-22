- **`edges.md` names the allocation bound set far above what the call allocates.** A bound two to
  three orders of magnitude above the measured bytes passes the temporary array that its clause
  forbids; the line asks for a bound from the count of the allocated arrays, checked against one
  more array of the forbidden size.
