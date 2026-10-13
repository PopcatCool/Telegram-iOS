// MARK: Burmaldagram
import SGSimpleSettings
import Foundation
import Postbox

/// Set on a message that was deleted on the server but is kept locally
public class DeletedByOthersMessageAttribute: MessageAttribute {
    public let date: Int32

    public init(date: Int32) {
        self.date = date
    }

    required public init(decoder: PostboxDecoder) {
        self.date = decoder.decodeInt32ForKey("d", orElse: 0)
    }

    public func encode(_ encoder: PostboxEncoder) {
        encoder.encodeInt32(self.date, forKey: "d")
    }
}

public extension Message {
    var isDeletedByOthers: Bool {
        for attribute in self.attributes {
            if attribute is DeletedByOthersMessageAttribute {
                return true
            }
        }
        return false
    }
}

func burmaldaShouldKeepDeletedMessages() -> Bool {
    return SGSimpleSettings.shared.keepDeletedMessages
}

/// Marks incoming cloud messages as deleted instead of removing them.
/// Returns the ids that still have to be deleted the usual way.
func burmaldaKeepDeletedMessages(transaction: Transaction, ids: [MessageId]) -> [MessageId] {
    if !SGSimpleSettings.shared.keepDeletedMessages {
        return ids
    }

    var remainingIds: [MessageId] = []
    let timestamp = Int32(CFAbsoluteTimeGetCurrent() + NSTimeIntervalSince1970)
    for id in ids {
        guard id.namespace == Namespaces.Message.Cloud, id.peerId.namespace != Namespaces.Peer.SecretChat, let message = transaction.getMessage(id), message.flags.contains(.Incoming) else {
            remainingIds.append(id)
            continue
        }
        if message.isDeletedByOthers {
            continue
        }
        transaction.updateMessage(id, update: { currentMessage in
            var attributes = currentMessage.attributes
            attributes.append(DeletedByOthersMessageAttribute(date: timestamp))
            return .update(StoreMessage(id: currentMessage.id, customStableId: nil, globallyUniqueId: currentMessage.globallyUniqueId, groupingKey: currentMessage.groupingKey, threadId: currentMessage.threadId, timestamp: currentMessage.timestamp, flags: StoreMessageFlags(currentMessage.flags), tags: currentMessage.tags, globalTags: currentMessage.globalTags, localTags: currentMessage.localTags, forwardInfo: currentMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init), authorId: currentMessage.author?.id, text: currentMessage.text, attributes: attributes, media: currentMessage.media))
        })
    }
    return remainingIds
}
