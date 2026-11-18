import Foundation
import SQLite3

enum LibraryError: LocalizedError {
    case missing(String)
    case open(String)

    var errorDescription: String? {
        switch self {
        case .missing(let s): return "Library file missing: \(s)"
        case .open(let s): return "Library could not be opened: \(s)"
        }
    }
}

/// Read only access to the bundled survival library (SQLite + FTS5 BM25).
/// `matchQuery` mirrors pipeline/search.py build_match_query; keep them in sync.
final class LibraryStore {
    private var db: OpaquePointer?
    private(set) var stopwords: Set<String> = []
    private(set) var categories: [SurvivalCategory] = []
    private(set) var chunkCount = 0

    init(url: URL) throws {
        guard FileManager.default.fileExists(atPath: url.path) else { throw LibraryError.missing(url.lastPathComponent) }
        if sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READONLY, nil) != SQLITE_OK {
            throw LibraryError.open(String(cString: sqlite3_errmsg(db)))
        }
        stopwords = Set(rows("SELECT word FROM stopwords") { Self.text($0, 0) })
        if let json = meta("categories")?.data(using: .utf8),
           let cats = try? JSONDecoder().decode([SurvivalCategory].self, from: json) {
            categories = cats
        }
        chunkCount = Int(meta("chunk_count") ?? "0") ?? 0
    }

    deinit { sqlite3_close(db) }

    func meta(_ key: String) -> String? {
        rows("SELECT value FROM meta WHERE key = ?", bind: [key]) { Self.text($0, 0) }.first
    }

    func matchQuery(_ question: String, category: String?) -> String {
        var text = question.lowercased().replacingOccurrences(of: "'", with: "")
        if let category, let cat = categories.first(where: { $0.id == category }) {
            text += " " + cat.terms
        }
        var seen: [String] = []
        for m in text.matches(of: #/[a-z0-9]+/#) {
            let tok = String(m.output)
            if tok.count > 1, !stopwords.contains(tok), !seen.contains(tok) { seen.append(tok) }
        }
        return seen.prefix(24).map { "\"\($0)\"" }.joined(separator: " OR ")
    }

    func search(_ question: String, category: String?, k: Int = 3) -> [LibraryChunk] {
        let q = matchQuery(question, category: category)
        guard !q.isEmpty else { return [] }
        let sql = """
        SELECT c.id, c.doc_short, c.chapter, c.page_start, c.page_end, c.text, bm25(chunks_fts) AS score
        FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?
        """
        return rows(sql, bind: [q, k], map: Self.chunk)
    }

    func chunks(ids: [Int64]) -> [LibraryChunk] {
        guard !ids.isEmpty else { return [] }
        let marks = Array(repeating: "?", count: ids.count).joined(separator: ",")
        let found = rows("SELECT id, doc_short, chapter, page_start, page_end, text FROM chunks WHERE id IN (\(marks))",
                         bind: ids, map: Self.chunk)
        return ids.compactMap { id in found.first { $0.id == id } }
    }

    func fieldCards() -> [FieldCard] {
        rows("SELECT id, title, subtitle, category, reviewed, chunk_ids_json FROM field_cards ORDER BY rowid") { s in
            let json = Self.text(s, 5)
            let ids = (try? JSONDecoder().decode([Int64].self, from: Data(json.utf8))) ?? []
            return FieldCard(id: Self.text(s, 0),
                             title: Self.text(s, 1),
                             subtitle: Self.text(s, 2),
                             category: Self.text(s, 3),
                             reviewed: sqlite3_column_int(s, 4) == 1,
                             chunkIds: ids)
        }
    }

    // MARK: SQLite plumbing

    private static func text(_ s: OpaquePointer, _ i: Int32) -> String {
        guard let p = sqlite3_column_text(s, i) else { return "" }
        return String(cString: p)
    }

    private static func chunk(_ s: OpaquePointer) -> LibraryChunk {
        LibraryChunk(id: sqlite3_column_int64(s, 0),
                     docShort: Self.text(s, 1),
                     chapter: Self.text(s, 2),
                     pageStart: Int(sqlite3_column_int(s, 3)),
                     pageEnd: Int(sqlite3_column_int(s, 4)),
                     text: Self.text(s, 5))
    }

    private static let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    private func rows<T>(_ sql: String, bind: [Any] = [], map: (OpaquePointer) -> T) -> [T] {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else { return [] }
        defer { sqlite3_finalize(stmt) }
        for (i, value) in bind.enumerated() {
            let idx = Int32(i + 1)
            switch value {
            case let v as String: sqlite3_bind_text(stmt, idx, v, -1, Self.transient)
            case let v as Int: sqlite3_bind_int64(stmt, idx, Int64(v))
            case let v as Int64: sqlite3_bind_int64(stmt, idx, v)
            default: sqlite3_bind_null(stmt, idx)
            }
        }
        var out: [T] = []
        while sqlite3_step(stmt) == SQLITE_ROW { out.append(map(stmt)) }
        return out
    }
}
