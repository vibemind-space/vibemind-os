/**
 * OCR Extraction Panel Component
 * Real-time OCR extraction monitoring and control
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Play, Pause, RotateCcw, Clock, Send, Settings, FileText, Target } from 'lucide-react';
import { OCRRegion, LiveDesktopConfig } from '@/types/liveDesktop';
import { useToast } from '@/hooks/use-toast';

interface OCRExtractionPanelProps {
  config: LiveDesktopConfig;
  regions: OCRRegion[];
  onConfigUpdate: (updates: Partial<LiveDesktopConfig>) => void;
  onExtractNow: () => void;
  isExtracting: boolean;
  lastExtractionTime?: Date;
  nextExtractionTime?: Date;
}

export const OCRExtractionPanel: React.FC<OCRExtractionPanelProps> = ({
  config,
  regions,
  onConfigUpdate,
  onExtractNow,
  isExtracting,
  lastExtractionTime,
  nextExtractionTime
}) => {
  const [intervalTimer, setIntervalTimer] = useState<NodeJS.Timeout | null>(null);
  const [timeUntilNext, setTimeUntilNext] = useState<number>(0);
  const { toast } = useToast();

  // Update countdown timer
  useEffect(() => {
    if (nextExtractionTime && config.ocr.enabled) {
      const timer = setInterval(() => {
        const now = new Date().getTime();
        const nextTime = nextExtractionTime.getTime();
        const diff = Math.max(0, Math.floor((nextTime - now) / 1000));
        setTimeUntilNext(diff);
      }, 1000);

      return () => clearInterval(timer);
    }
  }, [nextExtractionTime, config.ocr.enabled]);

  const activeRegions = regions.filter(r => r.isActive);
  const hasRegions = regions.length > 0;

  const handleOCRToggle = (enabled: boolean) => {
    onConfigUpdate({
      ocr: { ...config.ocr, enabled }
    });

    toast({
      title: enabled ? "OCR Enabled" : "OCR Disabled",
      description: enabled 
        ? `OCR extraction will run every ${config.ocr.extractionInterval} seconds`
        : "OCR extraction has been stopped",
    });
  };

  const handleIntervalChange = (interval: number) => {
    onConfigUpdate({
      ocr: { ...config.ocr, extractionInterval: interval }
    });
  };

  const handleWebhookUrlChange = (url: string) => {
    onConfigUpdate({
      ocr: { ...config.ocr, n8nWebhookUrl: url }
    });
  };

  const handleAutoSendToggle = (autoSend: boolean) => {
    onConfigUpdate({
      ocr: { ...config.ocr, autoSend }
    });
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-4">
      {/* OCR Status Overview */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5" />
            OCR Extraction Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-3 bg-muted rounded-lg">
              <div className="text-2xl font-bold text-primary">
                {activeRegions.length}
              </div>
              <div className="text-sm text-muted-foreground">Active Regions</div>
            </div>
            
            <div className="text-center p-3 bg-muted rounded-lg">
              <div className="text-2xl font-bold">
                {config.ocr.enabled ? (
                  <Badge variant="default">Running</Badge>
                ) : (
                  <Badge variant="secondary">Stopped</Badge>
                )}
              </div>
              <div className="text-sm text-muted-foreground">Extraction Status</div>
            </div>
            
            <div className="text-center p-3 bg-muted rounded-lg">
              <div className="text-2xl font-bold text-orange-600">
                {config.ocr.enabled && nextExtractionTime ? formatTime(timeUntilNext) : '--:--'}
              </div>
              <div className="text-sm text-muted-foreground">Next Extraction</div>
            </div>
          </div>

          {lastExtractionTime && (
            <div className="text-sm text-muted-foreground text-center">
              Last extraction: {lastExtractionTime.toLocaleTimeString()}
            </div>
          )}
        </CardContent>
      </Card>

      {/* OCR Controls */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle>Extraction Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Enable/Disable OCR */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label>Enable OCR Extraction</Label>
              <p className="text-sm text-muted-foreground">
                Automatically extract text from active regions
              </p>
            </div>
            <Switch
              checked={config.ocr.enabled}
              onCheckedChange={handleOCRToggle}
              disabled={!hasRegions}
            />
          </div>

          <Separator />

          {/* Extraction Interval */}
          <div className="space-y-2">
            <Label htmlFor="interval">Extraction Interval (seconds)</Label>
            <div className="flex items-center space-x-2">
              <Input
                id="interval"
                type="number"
                min="5"
                max="3600"
                value={config.ocr.extractionInterval}
                onChange={(e) => handleIntervalChange(parseInt(e.target.value) || 30)}
                className="w-24"
              />
              <span className="text-sm text-muted-foreground">
                Extract every {config.ocr.extractionInterval} seconds
              </span>
            </div>
          </div>

          <Separator />

          {/* Manual Extraction */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label>Manual Extraction</Label>
              <p className="text-sm text-muted-foreground">
                Extract text from all active regions now
              </p>
            </div>
            <Button
              onClick={onExtractNow}
              disabled={!hasRegions || activeRegions.length === 0 || isExtracting}
              size="sm"
            >
              {isExtracting ? (
                <>
                  <RotateCcw className="w-4 h-4 mr-2 animate-spin" />
                  Extracting...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Extract Now
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Webhook Configuration */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2">
            <Send className="w-5 h-5" />
            N8N Webhook Integration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="webhookUrl">Webhook URL</Label>
            <Input
              id="webhookUrl"
              type="url"
              placeholder="https://your-n8n-instance.com/webhook/ocr-data"
              value={config.ocr.n8nWebhookUrl || ''}
              onChange={(e) => handleWebhookUrlChange(e.target.value)}
            />
            <p className="text-sm text-muted-foreground">
              N8N webhook endpoint to receive extracted OCR data
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <Label>Auto-send to Webhook</Label>
              <p className="text-sm text-muted-foreground">
                Automatically send extracted data to webhook
              </p>
            </div>
            <Switch
              checked={config.ocr.autoSend}
              onCheckedChange={handleAutoSendToggle}
              disabled={!config.ocr.n8nWebhookUrl}
            />
          </div>
        </CardContent>
      </Card>

      {/* Region Summary */}
      {regions.length > 0 && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle>Region Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {regions.map((region, index) => (
                <div key={region.id} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Target className="w-3 h-3" />
                    <span>{region.label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={region.isActive ? "default" : "secondary"} className="text-xs">
                      {region.isActive ? "Active" : "Inactive"}
                    </Badge>
                    {region.lastExtractedText && (
                      <Badge variant="outline" className="text-xs">
                        Has Text
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* No Regions Warning */}
      {!hasRegions && (
        <Card className="border-orange-200 bg-orange-50">
          <CardContent className="pt-6">
            <div className="text-center text-orange-800">
              <Settings className="w-8 h-8 mx-auto mb-2" />
              <p className="font-medium">No OCR Regions Defined</p>
              <p className="text-sm text-orange-600 mt-1">
                Create OCR regions in the designer tab to enable text extraction
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};