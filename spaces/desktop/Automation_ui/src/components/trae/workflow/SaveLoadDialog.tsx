
import React, { useState, useRef } from 'react';
import { Node, Edge } from '@xyflow/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Save, Upload, Download, Trash2, FolderOpen } from 'lucide-react';
import { toast } from 'sonner';
import { WorkflowStorage, SavedWorkflow } from '@/utils/workflowStorage';

interface SaveLoadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  nodes: Node[];
  edges: Edge[];
  onLoadWorkflow: (nodes: Node[], edges: Edge[]) => void;
}

export const SaveLoadDialog: React.FC<SaveLoadDialogProps> = ({
  isOpen,
  onClose,
  nodes,
  edges,
  onLoadWorkflow
}) => {
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDescription, setWorkflowDescription] = useState('');
  const [savedWorkflows, setSavedWorkflows] = useState<SavedWorkflow[]>(() => 
    WorkflowStorage.getAllWorkflows()
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSave = () => {
    if (!workflowName.trim()) {
      toast.error('Please enter a workflow name');
      return;
    }

    try {
      const savedWorkflow = WorkflowStorage.saveWorkflow({
        name: workflowName.trim(),
        description: workflowDescription.trim(),
        nodes,
        edges
      });

      setSavedWorkflows(WorkflowStorage.getAllWorkflows());
      setWorkflowName('');
      setWorkflowDescription('');
      
      toast.success(`Workflow "${savedWorkflow.name}" saved successfully!`);
    } catch (error) {
      toast.error('Failed to save workflow');
    }
  };

  const handleLoad = (workflow: SavedWorkflow) => {
    try {
      onLoadWorkflow(workflow.nodes, workflow.edges);
      toast.success(`Workflow "${workflow.name}" loaded successfully!`);
      onClose();
    } catch (error) {
      toast.error('Failed to load workflow');
    }
  };

  const handleDelete = (id: string, name: string) => {
    if (confirm(`Are you sure you want to delete "${name}"?`)) {
      WorkflowStorage.deleteWorkflow(id);
      setSavedWorkflows(WorkflowStorage.getAllWorkflows());
      toast.success('Workflow deleted');
    }
  };

  const handleExport = (id: string, name: string) => {
    const jsonData = WorkflowStorage.exportWorkflow(id);
    if (!jsonData) {
      toast.error('Failed to export workflow');
      return;
    }

    const blob = new Blob([jsonData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name.replace(/[^a-z0-9]/gi, '_')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    toast.success('Workflow exported successfully!');
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      const imported = WorkflowStorage.importWorkflow(content);
      
      if (imported) {
        setSavedWorkflows(WorkflowStorage.getAllWorkflows());
        toast.success(`Workflow "${imported.name}" imported successfully!`);
      } else {
        toast.error('Failed to import workflow. Invalid file format.');
      }
    };
    
    reader.readAsText(file);
    event.target.value = '';
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>Save & Load Workflows</DialogTitle>
          <DialogDescription>
            Save your current workflow or load a previously saved one
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="save" className="flex-1 overflow-hidden">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="save">Save</TabsTrigger>
            <TabsTrigger value="load">Load</TabsTrigger>
            <TabsTrigger value="import">Import/Export</TabsTrigger>
          </TabsList>

          <TabsContent value="save" className="space-y-4">
            <div className="space-y-4">
              <div>
                <Label htmlFor="workflowName">Workflow Name *</Label>
                <Input
                  id="workflowName"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="Enter workflow name..."
                  className="mt-1"
                />
              </div>
              
              <div>
                <Label htmlFor="workflowDescription">Description</Label>
                <Textarea
                  id="workflowDescription"
                  value={workflowDescription}
                  onChange={(e) => setWorkflowDescription(e.target.value)}
                  placeholder="Optional description..."
                  className="mt-1"
                  rows={3}
                />
              </div>

              <div className="flex justify-between items-center pt-2">
                <div className="text-sm text-muted-foreground">
                  Current workflow: {nodes.length} nodes, {edges.length} connections
                </div>
                <Button onClick={handleSave} disabled={!workflowName.trim()}>
                  <Save className="w-4 h-4 mr-2" />
                  Save Workflow
                </Button>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="load" className="space-y-4">
            <div className="max-h-96 overflow-y-auto space-y-2">
              {savedWorkflows.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderOpen className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  No saved workflows found
                </div>
              ) : (
                savedWorkflows.map((workflow) => (
                  <Card key={workflow.id} className="relative">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <CardTitle className="text-base">{workflow.name}</CardTitle>
                          {workflow.description && (
                            <p className="text-sm text-muted-foreground mt-1">
                              {workflow.description}
                            </p>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(workflow.id, workflow.name)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center justify-between">
                        <div className="flex space-x-2">
                          <Badge variant="outline">
                            {workflow.nodes.length} nodes
                          </Badge>
                          <Badge variant="outline">
                            {workflow.edges.length} connections
                          </Badge>
                        </div>
                        <div className="flex space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleExport(workflow.id, workflow.name)}
                          >
                            <Download className="w-4 h-4 mr-1" />
                            Export
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleLoad(workflow)}
                          >
                            Load
                          </Button>
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground mt-2">
                        Saved: {new Date(workflow.createdAt).toLocaleString()}
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="import" className="space-y-4">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Button
                  variant="outline"
                  onClick={handleImport}
                  className="h-20 flex-col"
                >
                  <Upload className="w-6 h-6 mb-2" />
                  Import Workflow
                </Button>
                
                <div className="flex flex-col justify-center">
                  <p className="text-sm text-muted-foreground mb-2">
                    Import a workflow from a JSON file
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Supports .json files exported from this application
                  </p>
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileSelect}
                className="hidden"
              />
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};
