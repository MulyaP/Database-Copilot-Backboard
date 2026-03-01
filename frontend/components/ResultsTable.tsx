interface ResultsTableProps {
  columns: string[];
  rows: unknown[][];
}

export default function ResultsTable({ columns, rows }: ResultsTableProps) {
  if (rows.length === 0) {
    return (
      <p className="mt-2 text-xs text-gray-500">Query returned 0 rows.</p>
    );
  }

  return (
    <div className="mt-2 overflow-x-auto rounded border border-gray-200">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-gray-100">
            {columns.map((col) => (
              <th
                key={col}
                className="border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold text-gray-600"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={ri}
              className={ri % 2 === 0 ? "bg-white" : "bg-gray-50"}
            >
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className="border-b border-gray-100 px-3 py-2 text-xs text-gray-700"
                >
                  {cell === null ? (
                    <span className="text-gray-400">NULL</span>
                  ) : (
                    String(cell)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="bg-gray-50 px-3 py-1.5 text-xs text-gray-400">
        {rows.length} row{rows.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}
