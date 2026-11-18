import Foundation

/// Builds the exact user message used in training (training/prompt_format.py).
/// Any change here must be made there too, or the fine tune stops matching.
enum PromptBuilder {
    static func userMessage(question: String, categoryLabel: String?, sources: [LibraryChunk]) -> String {
        var lines: [String] = []
        if let categoryLabel { lines.append("SITUATION: \(categoryLabel)") }
        lines.append("QUESTION: \(question.trimmingCharacters(in: .whitespacesAndNewlines))")
        lines.append("")
        lines.append("SOURCES:")
        if sources.isEmpty { lines.append("(none found)") }
        for (i, s) in sources.enumerated() {
            lines.append("[S\(i + 1)] (\(s.label))")
            lines.append(s.text.trimmingCharacters(in: .whitespacesAndNewlines))
            lines.append("")
        }
        while lines.last == "" { lines.removeLast() }
        return lines.joined(separator: "\n")
    }

    static var systemPrompt: String {
        guard let url = Bundle.main.url(forResource: "runtime_system", withExtension: "txt"),
              let text = try? String(contentsOf: url, encoding: .utf8) else {
            return "Answer only from the SOURCES. If they do not contain the answer, reply NOT IN LIBRARY."
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
