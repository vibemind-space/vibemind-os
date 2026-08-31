import TwiML from "twilio/lib/twiml/TwiML";
import VoiceResponse from "twilio/lib/twiml/VoiceResponse";
import { z } from "zod";

export function XmlResponse(content: TwiML) {
    return new Response(content.toString(), {
        headers: {
            "Content-Type": "text/xml",
        },
    });
}

export function reject(reason: VoiceResponse.RejectAttributes['reason']) {
    return XmlResponse(new VoiceResponse()
        .reject({
            reason,
        })
    );
}

export function hangup() {
    return XmlResponse(new VoiceResponse()
        .hangup()
    );
}

export const ZStandardRequestParams = z.object({
    To: z.string(),
    Direction: z.literal('inbound'),
    CallSid: z.string(),
    From: z.string(),
});