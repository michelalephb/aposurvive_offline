import AVFoundation
import Foundation

/// Flashes SOS in Morse code with the camera torch until stopped.
@MainActor
final class SOSTorch: ObservableObject {
    @Published private(set) var running = false
    private var task: Task<Void, Never>?

    private let unit: UInt64 = 200_000_000  // 200 ms per Morse unit

    var available: Bool { AVCaptureDevice.default(for: .video)?.hasTorch ?? false }

    func toggle() { running ? stop() : start() }

    func start() {
        guard available, !running else { return }
        running = true
        // S = ... , O = --- ; dot 1 unit, dash 3, gap 1, letter gap 3, word gap 7
        let pattern: [(on: Bool, units: UInt64)] =
            [(true, 1), (false, 1), (true, 1), (false, 1), (true, 1), (false, 3),
             (true, 3), (false, 1), (true, 3), (false, 1), (true, 3), (false, 3),
             (true, 1), (false, 1), (true, 1), (false, 1), (true, 1), (false, 7)]
        task = Task { [unit] in
            while !Task.isCancelled {
                for step in pattern {
                    Self.setTorch(step.on)
                    try? await Task.sleep(nanoseconds: step.units * unit)
                    if Task.isCancelled { break }
                }
            }
            Self.setTorch(false)
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        running = false
        Self.setTorch(false)
    }

    private static func setTorch(_ on: Bool) {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return }
        do {
            try device.lockForConfiguration()
            device.torchMode = on ? .on : .off
            device.unlockForConfiguration()
        } catch {}
    }
}
