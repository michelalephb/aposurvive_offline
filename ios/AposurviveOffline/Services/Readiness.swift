import CryptoKit
import Foundation

/// "Offline OK" is shown only when every piece needed with no network is verified on the phone.
struct Readiness {
    var libraryOK = false
    var libraryDetail = "Not checked"
    var promptOK = false
    var modelOK = false
    var modelDetail = "Not downloaded"

    var offlineOK: Bool { libraryOK && promptOK && modelOK }

    @MainActor
    static func check(library: LibraryStore?) -> Readiness {
        var r = Readiness()

        // Library: file present, sha256 matches the manifest written by pipeline.build_library
        if let db = Bundle.main.url(forResource: "library", withExtension: "sqlite"),
           let manURL = Bundle.main.url(forResource: "library_manifest", withExtension: "json"),
           let manData = try? Data(contentsOf: manURL),
           let manifest = try? JSONSerialization.jsonObject(with: manData) as? [String: Any],
           let expected = manifest["sha256"] as? String {
            let actual = sha256(of: db)
            if actual == expected, let library, library.chunkCount > 0 {
                r.libraryOK = true
                r.libraryDetail = "\(library.chunkCount) passages, built \(manifest["built_at"] as? String ?? "?")"
            } else {
                r.libraryDetail = actual == expected ? "Library empty" : "Checksum mismatch"
            }
        } else {
            r.libraryDetail = "Library not bundled (run scripts/sync_ios_resources.sh)"
        }

        r.promptOK = Bundle.main.url(forResource: "runtime_system", withExtension: "txt") != nil

        if ModelService.isDownloaded {
            r.modelOK = true
            let gb = Double(ModelService.downloadedBytes) / 1_000_000_000
            r.modelDetail = String(format: "%.1f GB on device", gb)
        }
        return r
    }

    static func sha256(of url: URL) -> String? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try? handle.read(upToCount: 1 << 20), !data.isEmpty {
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
