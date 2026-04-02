/**
 * MediaProcessor Komponente für TRAE Unity AI Platform
 * Bietet UI für Video- und Audio-Verarbeitung mit FFmpeg
 */

import React, { useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Video, 
  Music, 
  Image, 
  Download, 
  Upload, 
  Play, 
  Pause, 
  Settings,
  FileVideo,
  FileAudio,
  Scissors,
  Combine,
  Archive
} from 'lucide-react';

interface MediaFile {
  name: string;
  path: string;
  type: 'video' | 'audio' | 'image';
  size: number;
  duration?: string;
  resolution?: string;
  fps?: number;
}

interface ProcessingJob {
  id: string;
  type: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  progress: number;
  input: string;
  output: string;
  error?: string;
}

const MediaProcessor: React.FC = () => {
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [selectedFile, setSelectedFile] = useState<MediaFile | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Datei-Upload Handler
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFiles = Array.from(event.target.files || []);
    
    uploadedFiles.forEach(file => {
      const mediaFile: MediaFile = {
        name: file.name,
        path: URL.createObjectURL(file),
        type: getFileType(file.name),
        size: file.size
      };
      
      setFiles(prev => [...prev, mediaFile]);
    });
  };

  // Dateityp bestimmen
  const getFileType = (filename: string): 'video' | 'audio' | 'image' => {
    const ext = filename.toLowerCase().split('.').pop();
    
    if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext || '')) {
      return 'video';
    } else if (['mp3', 'wav', 'aac', 'flac', 'ogg'].includes(ext || '')) {
      return 'audio';
    } else {
      return 'image';
    }
  };

  // Dateigröße formatieren
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Video konvertieren
  const handleVideoConvert = async (format: string) => {
    if (!selectedFile) return;

    const jobId = Date.now().toString();
    const newJob: ProcessingJob = {
      id: jobId,
      type: `Video zu ${format.toUpperCase()}`,
      status: 'pending',
      progress: 0,
      input: selectedFile.name,
      output: `${selectedFile.name.split('.')[0]}.${format}`
    };

    setJobs(prev => [...prev, newJob]);
    setIsProcessing(true);

    try {
      // Simuliere FFmpeg-Verarbeitung
      await simulateProcessing(jobId);
      
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'completed', progress: 100 }
          : job
      ));
    } catch (error) {
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'error', error: 'Konvertierung fehlgeschlagen' }
          : job
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  // Audio extrahieren
  const handleAudioExtract = async () => {
    if (!selectedFile || selectedFile.type !== 'video') return;

    const jobId = Date.now().toString();
    const newJob: ProcessingJob = {
      id: jobId,
      type: 'Audio-Extraktion',
      status: 'pending',
      progress: 0,
      input: selectedFile.name,
      output: `${selectedFile.name.split('.')[0]}.mp3`
    };

    setJobs(prev => [...prev, newJob]);
    setIsProcessing(true);

    try {
      await simulateProcessing(jobId);
      
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'completed', progress: 100 }
          : job
      ));
    } catch (error) {
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'error', error: 'Audio-Extraktion fehlgeschlagen' }
          : job
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  // Thumbnail erstellen
  const handleThumbnailCreate = async () => {
    if (!selectedFile || selectedFile.type !== 'video') return;

    const jobId = Date.now().toString();
    const newJob: ProcessingJob = {
      id: jobId,
      type: 'Thumbnail-Erstellung',
      status: 'pending',
      progress: 0,
      input: selectedFile.name,
      output: `${selectedFile.name.split('.')[0]}_thumb.jpg`
    };

    setJobs(prev => [...prev, newJob]);
    setIsProcessing(true);

    try {
      await simulateProcessing(jobId);
      
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'completed', progress: 100 }
          : job
      ));
    } catch (error) {
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'error', error: 'Thumbnail-Erstellung fehlgeschlagen' }
          : job
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  // Video komprimieren
  const handleVideoCompress = async (quality: string) => {
    if (!selectedFile || selectedFile.type !== 'video') return;

    const jobId = Date.now().toString();
    const newJob: ProcessingJob = {
      id: jobId,
      type: `Video-Komprimierung (${quality})`,
      status: 'pending',
      progress: 0,
      input: selectedFile.name,
      output: `${selectedFile.name.split('.')[0]}_compressed.mp4`
    };

    setJobs(prev => [...prev, newJob]);
    setIsProcessing(true);

    try {
      await simulateProcessing(jobId);
      
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'completed', progress: 100 }
          : job
      ));
    } catch (error) {
      setJobs(prev => prev.map(job => 
        job.id === jobId 
          ? { ...job, status: 'error', error: 'Komprimierung fehlgeschlagen' }
          : job
      ));
    } finally {
      setIsProcessing(false);
    }
  };

  // Verarbeitung simulieren
  const simulateProcessing = async (jobId: string): Promise<void> => {
    return new Promise((resolve) => {
      let progress = 0;
      const interval = setInterval(() => {
        progress += Math.random() * 20;
        if (progress >= 100) {
          progress = 100;
          clearInterval(interval);
          resolve();
        }
        
        setJobs(prev => prev.map(job => 
          job.id === jobId 
            ? { ...job, status: 'processing', progress: Math.round(progress) }
            : job
        ));
      }, 500);
    });
  };

  // Status-Badge Farbe
  const getStatusColor = (status: ProcessingJob['status']) => {
    switch (status) {
      case 'pending': return 'bg-yellow-500';
      case 'processing': return 'bg-blue-500';
      case 'completed': return 'bg-green-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Media Processor</h2>
          <p className="text-muted-foreground">
            Video- und Audio-Verarbeitung mit FFmpeg
          </p>
        </div>
        <Button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-2"
        >
          <Upload className="h-4 w-4" />
          Dateien hochladen
        </Button>
      </div>

      {/* Versteckter File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="video/*,audio/*,image/*"
        onChange={handleFileUpload}
        className="hidden"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Dateiliste */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileVideo className="h-5 w-5" />
              Dateien ({files.length})
            </CardTitle>
            <CardDescription>
              Wählen Sie eine Datei zur Verarbeitung aus
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {files.map((file, index) => (
                <div
                  key={index}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedFile?.name === file.name
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-muted/50'
                  }`}
                  onClick={() => setSelectedFile(file)}
                >
                  <div className="flex items-center gap-2">
                    {file.type === 'video' && <Video className="h-4 w-4" />}
                    {file.type === 'audio' && <Music className="h-4 w-4" />}
                    {file.type === 'image' && <Image className="h-4 w-4" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(file.size)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
              
              {files.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <FileVideo className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Keine Dateien hochgeladen</p>
                  <p className="text-xs">Klicken Sie auf "Dateien hochladen"</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Verarbeitungsoptionen */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Verarbeitung
            </CardTitle>
            <CardDescription>
              {selectedFile ? `Ausgewählt: ${selectedFile.name}` : 'Keine Datei ausgewählt'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {selectedFile ? (
              <Tabs defaultValue="convert" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="convert">Format</TabsTrigger>
                  <TabsTrigger value="extract">Audio</TabsTrigger>
                  <TabsTrigger value="thumbnail">Thumb</TabsTrigger>
                  <TabsTrigger value="compress">Kompr.</TabsTrigger>
                </TabsList>
                
                <TabsContent value="convert" className="space-y-4">
                  <div>
                    <Label>Zielformat</Label>
                    <Select onValueChange={handleVideoConvert}>
                      <SelectTrigger>
                        <SelectValue placeholder="Format wählen" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="mp4">MP4</SelectItem>
                        <SelectItem value="avi">AVI</SelectItem>
                        <SelectItem value="mov">MOV</SelectItem>
                        <SelectItem value="webm">WebM</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </TabsContent>
                
                <TabsContent value="extract" className="space-y-4">
                  <Button 
                    onClick={handleAudioExtract}
                    disabled={selectedFile.type !== 'video' || isProcessing}
                    className="w-full"
                  >
                    <FileAudio className="h-4 w-4 mr-2" />
                    Audio als MP3 extrahieren
                  </Button>
                </TabsContent>
                
                <TabsContent value="thumbnail" className="space-y-4">
                  <Button 
                    onClick={handleThumbnailCreate}
                    disabled={selectedFile.type !== 'video' || isProcessing}
                    className="w-full"
                  >
                    <Image className="h-4 w-4 mr-2" />
                    Thumbnail erstellen
                  </Button>
                </TabsContent>
                
                <TabsContent value="compress" className="space-y-4">
                  <div>
                    <Label>Qualität</Label>
                    <Select onValueChange={handleVideoCompress}>
                      <SelectTrigger>
                        <SelectValue placeholder="Qualität wählen" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="high">Hoch (CRF 18)</SelectItem>
                        <SelectItem value="medium">Mittel (CRF 23)</SelectItem>
                        <SelectItem value="low">Niedrig (CRF 28)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </TabsContent>
              </Tabs>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Settings className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p>Wählen Sie eine Datei aus</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Verarbeitungsjobs */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Play className="h-5 w-5" />
              Jobs ({jobs.length})
            </CardTitle>
            <CardDescription>
              Aktuelle und abgeschlossene Verarbeitungen
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {jobs.map((job) => (
                <div key={job.id} className="p-3 rounded-lg border">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium">{job.type}</p>
                    <Badge className={getStatusColor(job.status)}>
                      {job.status}
                    </Badge>
                  </div>
                  
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">
                      {job.input} → {job.output}
                    </p>
                    
                    {job.status === 'processing' && (
                      <Progress value={job.progress} className="h-2" />
                    )}
                    
                    {job.error && (
                      <p className="text-xs text-red-500">{job.error}</p>
                    )}
                    
                    {job.status === 'completed' && (
                      <Button size="sm" variant="outline" className="w-full mt-2">
                        <Download className="h-3 w-3 mr-1" />
                        Download
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              
              {jobs.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <Play className="h-12 w-12 mx-auto mb-2 opacity-50" />
                  <p>Keine Jobs</p>
                  <p className="text-xs">Starten Sie eine Verarbeitung</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default MediaProcessor;