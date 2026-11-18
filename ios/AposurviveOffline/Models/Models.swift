import Foundation

struct SurvivalCategory: Identifiable, Hashable, Decodable {
    let id: String
    let label: String
    let terms: String

    var symbol: String {
        switch id {
        case "injury": return "cross.case"
        case "water": return "drop"
        case "fire": return "flame"
        case "shelter": return "tent"
        case "navigate": return "location.north.circle"
        case "food": return "leaf"
        case "signal": return "light.beacon.max"
        case "cold_heat": return "thermometer.medium"
        default: return "questionmark.circle"
        }
    }

    var isUrgent: Bool { id == "injury" }
}

struct LibraryChunk: Identifiable, Hashable {
    let id: Int64
    let docShort: String
    let chapter: String
    let pageStart: Int
    let pageEnd: Int
    let text: String

    /// Must match pipeline/search.py source_label exactly (it is part of the trained prompt).
    var label: String {
        let pages = pageStart == pageEnd ? "p \(pageStart)" : "pp \(pageStart) to \(pageEnd)"
        return "\(docShort), ch \(chapter), \(pages)"
    }

    var shortLabel: String { "\(docShort) ch \(chapter)" }
}

struct FieldCard: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let category: String
    let reviewed: Bool
    let chunkIds: [Int64]
}

/// Parsed form of the runtime reply format defined in training/prompts/runtime_system.txt.
struct ParsedReply: Equatable {
    enum Kind: Equatable { case answer, refusal, unknown }

    var kind: Kind = .unknown
    var steps: [String] = []
    var sourceRefs: [Int] = []
    var refusalText = ""
    var checks: [String] = []

    static func parse(_ text: String) -> ParsedReply {
        var r = ParsedReply()
        let lines = text.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        guard let head = lines.first else { return r }
        var inCheck = false
        switch head {
        case "DO NOW": r.kind = .answer
        case "NOT IN LIBRARY": r.kind = .refusal
        default: return r
        }
        for line in lines.dropFirst() {
            if line == "CHECK" { inCheck = true; continue }
            if inCheck {
                if line.hasPrefix("- ") { r.checks.append(String(line.dropFirst(2))) }
                continue
            }
            if line.hasPrefix("SOURCES:") {
                r.sourceRefs = line.matches(of: #/\[S(\d+)\]/#).compactMap { Int($0.1) }
            } else if r.kind == .answer, let m = line.firstMatch(of: #/^\d+\.\s+(.+)$/#) {
                r.steps.append(String(m.1))
            } else if r.kind == .refusal {
                r.refusalText += (r.refusalText.isEmpty ? "" : " ") + line
            }
        }
        return r
    }
}

struct ChatTurn: Identifiable {
    enum Role { case user, assistant, libraryOnly, blocked }

    let id = UUID()
    let role: Role
    var text: String
    var sources: [LibraryChunk] = []
    var tokensPerSecond: Double?
    var finished = false

    var parsed: ParsedReply { ParsedReply.parse(text) }
}
