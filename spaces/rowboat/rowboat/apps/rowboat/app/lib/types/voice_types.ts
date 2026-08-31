import { z } from 'zod';
import { Message } from './types';

export const TwilioConfigParams = z.object({
    phone_number: z.string(),
    account_sid: z.string(),
    auth_token: z.string(),
    label: z.string(),
    project_id: z.string(),
});

export const TwilioConfig = TwilioConfigParams.extend({
    createdAt: z.date(),
    status: z.enum(['active', 'deleted']),
});

export interface TwilioConfigResponse {
    success: boolean;
    error?: string;
}

export interface InboundConfigResponse {
    status: 'configured' | 'reconfigured';
    phone_number: string;
    previous_webhook?: string;
    error?: string;
}

export const TwilioInboundCall = z.object({
    callSid: z.string(),
    to: z.string(),
    from: z.string(),
    projectId: z.string(),
    messages: z.array(Message),
    createdAt: z.string().datetime(),
    lastUpdatedAt: z.string().datetime().optional(),
})