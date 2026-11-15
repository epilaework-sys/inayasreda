#!/usr/bin/swift
import AVFoundation
import CoreImage
import Foundation

let src = URL(fileURLWithPath: CommandLine.arguments[1])
let dst = URL(fileURLWithPath: CommandLine.arguments[2])
let width = 1920
let height = 1080
let bitRate = 5_500_000

try? FileManager.default.removeItem(at: dst)

let asset = AVURLAsset(url: src)
guard let videoTrack = asset.tracks(withMediaType: .video).first else {
    fputs("no video track\n", stderr)
    exit(1)
}
let audioTrack = asset.tracks(withMediaType: .audio).first

let reader = try AVAssetReader(asset: asset)
if CommandLine.arguments.count > 3, let seconds = Double(CommandLine.arguments[3]), seconds > 0 {
    let start = CommandLine.arguments.count > 4 ? (Double(CommandLine.arguments[4]) ?? 0) : 0
    reader.timeRange = CMTimeRange(
        start: CMTime(seconds: start, preferredTimescale: 600),
        duration: CMTime(seconds: seconds, preferredTimescale: 600)
    )
}

let videoReader = AVAssetReaderTrackOutput(track: videoTrack, outputSettings: [
    kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)
])
videoReader.alwaysCopiesSampleData = false
reader.add(videoReader)

var audioReader: AVAssetReaderTrackOutput?
if let audioTrack {
    let out = AVAssetReaderTrackOutput(track: audioTrack, outputSettings: [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVLinearPCMIsFloatKey: false,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsNonInterleaved: false
    ])
    out.alwaysCopiesSampleData = false
    reader.add(out)
    audioReader = out
}

let writer = try AVAssetWriter(outputURL: dst, fileType: .mp4)
writer.shouldOptimizeForNetworkUse = true

let videoWriter = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: bitRate,
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        AVVideoMaxKeyFrameIntervalDurationKey: 2
    ]
])
videoWriter.expectsMediaDataInRealTime = false
writer.add(videoWriter)

let adaptor = AVAssetWriterInputPixelBufferAdaptor(
    assetWriterInput: videoWriter,
    sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height
    ]
)

var audioWriter: AVAssetWriterInput?
if audioReader != nil {
    let aw = AVAssetWriterInput(mediaType: .audio, outputSettings: [
        AVFormatIDKey: kAudioFormatMPEG4AAC,
        AVNumberOfChannelsKey: 2,
        AVSampleRateKey: 44100,
        AVEncoderBitRateKey: 128000
    ])
    aw.expectsMediaDataInRealTime = false
    writer.add(aw)
    audioWriter = aw
}

let ci = CIContext(options: [.useSoftwareRenderer: false])
let transform = videoTrack.preferredTransform

guard writer.startWriting(), reader.startReading() else {
    fputs("failed to start: \(writer.error?.localizedDescription ?? reader.error?.localizedDescription ?? "?")\n", stderr)
    exit(1)
}
writer.startSession(atSourceTime: reader.timeRange.start)

func makeBuffer() -> CVPixelBuffer? {
    if let pool = adaptor.pixelBufferPool {
        var buf: CVPixelBuffer?
        CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buf)
        return buf
    }
    var buf: CVPixelBuffer?
    let attrs: [CFString: Any] = [
        kCVPixelBufferPixelFormatTypeKey: Int(kCVPixelFormatType_32BGRA),
        kCVPixelBufferWidthKey: width,
        kCVPixelBufferHeightKey: height,
        kCVPixelBufferIOSurfacePropertiesKey: [:]
    ]
    CVPixelBufferCreate(nil, width, height, kCVPixelFormatType_32BGRA, attrs as CFDictionary, &buf)
    return buf
}

var videoDone = false
var audioDone = audioWriter == nil
var frames = 0

while !videoDone || !audioDone {
    var idle = true

    if !videoDone, videoWriter.isReadyForMoreMediaData {
        if let sample = videoReader.copyNextSampleBuffer(),
           let imageBuffer = CMSampleBufferGetImageBuffer(sample) {
            idle = false
            var image = CIImage(cvImageBuffer: imageBuffer).transformed(by: transform)
            let extent = image.extent
            let scale = min(CGFloat(width) / extent.width, CGFloat(height) / extent.height)
            image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
            let scaled = image.extent
            image = image.transformed(by: CGAffineTransform(
                translationX: (CGFloat(width) - scaled.width) / 2,
                y: (CGFloat(height) - scaled.height) / 2
            ))
            image = image.cropped(to: CGRect(x: 0, y: 0, width: width, height: height))
            if let outBuf = makeBuffer() {
                ci.render(image, to: outBuf, bounds: CGRect(x: 0, y: 0, width: width, height: height), colorSpace: CGColorSpaceCreateDeviceRGB())
                adaptor.append(outBuf, withPresentationTime: CMSampleBufferGetPresentationTimeStamp(sample))
                frames += 1
                if frames % 60 == 0 { fputs("frames \(frames)\n", stderr) }
            }
        } else {
            videoWriter.markAsFinished()
            videoDone = true
            idle = false
        }
    }

    if !audioDone, let audioWriter, let audioReader, audioWriter.isReadyForMoreMediaData {
        if let sample = audioReader.copyNextSampleBuffer() {
            audioWriter.append(sample)
            idle = false
        } else {
            audioWriter.markAsFinished()
            audioDone = true
            idle = false
        }
    }

    if idle { Thread.sleep(forTimeInterval: 0.002) }
}

let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()

if writer.status != .completed {
    fputs("write failed: \(writer.error?.localizedDescription ?? "unknown")\n", stderr)
    exit(1)
}
print("ok frames=\(frames) \(dst.path)")
