
import React, { useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Search,
  Filter,
  Eye,
  Edit3,
  Save,
  X,
  Copy,
  Download,
  Variable,
  Globe,
  Settings,
  ChevronRight,
  ChevronDown
} from 'lucide-react';
import type { NodeVariable, WorkflowVariable, VariableFilters } from '@/types/variables';

// Mock data for demonstration
const mockNodeVariables: Record<string, NodeVariable[]> = {
  'node-1': [
    {
      id: 'var-1',
      name: 'inputData',
      type: 'input',
      dataType: 'object',
      value: { x: 100, y: 200, action: 'click' },
      description: 'Mouse click coordinates and action',
      timestamp: new Date().toISOString()
    },
    {
      id: 'var-2',
      name: 'result',
      type: 'output',
      dataType: 'boolean',
      value: true,
      description: 'Click operation success status',
      timestamp: new Date().toISOString()
    }
  ],
  'node-2': [
    {
      id: 'var-3',
      name: 'textInput',
      type: 'input',
      dataType: 'string',
      value: 'Hello World',
      description: 'Text to be typed',
      timestamp: new Date().toISOString()
    }
  ]
};

const mockWorkflowVariables: WorkflowVariable[] = [
  {
    id: 'wf-var-1',
    name: 'API_BASE_URL',
    value: 'https://api.example.com',
    type: 'environment',
    dataType: 'string',
    description: 'Base URL for API calls',
    isEditable: true,
    lastModified: new Date().toISOString()
  },
  {
    id: 'wf-var-2',
    name: 'executionCount',
    value: 5,
    type: 'runtime',
    dataType: 'number',
    description: 'Number of workflow executions',
    isEditable: false,
    lastModified: new Date().toISOString()
  },
  {
    id: 'wf-var-3',
    name: 'config',
    value: { timeout: 30000, retries: 3, debug: true },
    type: 'global',
    dataType: 'object',
    description: 'Global workflow configuration',
    isEditable: true,
    lastModified: new Date().toISOString()
  }
];

interface ExpandedRows {
  [key: string]: boolean;
}

const WorkflowVariables: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string>('node-1');
  const [filters, setFilters] = useState<VariableFilters>({});
  const [editingVariable, setEditingVariable] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [expandedRows, setExpandedRows] = useState<ExpandedRows>({});

  // Format value for display
  const formatValue = (value: any, dataType: string): string => {
    if (value === null || value === undefined) return 'null';
    if (dataType === 'object' || dataType === 'array') {
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  };

  // Get type badge color
  const getTypeBadgeColor = (type: string) => {
    switch (type) {
      case 'input': return 'bg-blue-100 text-blue-800';
      case 'output': return 'bg-green-100 text-green-800';
      case 'config': return 'bg-purple-100 text-purple-800';
      case 'global': return 'bg-orange-100 text-orange-800';
      case 'environment': return 'bg-teal-100 text-teal-800';
      case 'runtime': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  // Filter node variables
  const filteredNodeVariables = useMemo(() => {
    const variables = mockNodeVariables[selectedNodeId] || [];
    return variables.filter(variable => {
      if (filters.type && variable.type !== filters.type) return false;
      if (filters.dataType && variable.dataType !== filters.dataType) return false;
      if (filters.search && !variable.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [selectedNodeId, filters]);

  // Filter workflow variables
  const filteredWorkflowVariables = useMemo(() => {
    return mockWorkflowVariables.filter(variable => {
      if (filters.type && variable.type !== filters.type) return false;
      if (filters.dataType && variable.dataType !== filters.dataType) return false;
      if (filters.search && !variable.name.toLowerCase().includes(filters.search.toLowerCase())) return false;
      return true;
    });
  }, [filters]);

  // Toggle row expansion
  const toggleRowExpansion = (id: string) => {
    setExpandedRows(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  // Handle variable editing
  const startEditing = (variable: WorkflowVariable) => {
    setEditingVariable(variable.id);
    setEditValue(formatValue(variable.value, variable.dataType));
  };

  const saveEdit = () => {
    // Here you would save the edited value
    console.log('Saving variable:', editingVariable, editValue);
    setEditingVariable(null);
    setEditValue('');
  };

  const cancelEdit = () => {
    setEditingVariable(null);
    setEditValue('');
  };

  // Copy variable value
  const copyValue = (value: any) => {
    navigator.clipboard.writeText(JSON.stringify(value, null, 2));
  };

  // Export variables
  const exportVariables = () => {
    const data = {
      nodeVariables: mockNodeVariables,
      workflowVariables: mockWorkflowVariables,
      timestamp: new Date().toISOString()
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'workflow-variables.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center space-x-3">
          <Variable className="w-5 h-5 text-purple-600" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">Variables</h3>
            <p className="text-xs text-muted-foreground">Node and workflow variables</p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="sm" onClick={exportVariables}>
            <Download className="w-4 h-4 mr-1" />
            Export
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="p-4 border-b bg-muted/30">
        <div className="flex items-center space-x-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search variables..."
              className="pl-10"
              value={filters.search || ''}
              onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
            />
          </div>
          <Button variant="outline" size="sm">
            <Filter className="w-4 h-4 mr-1" />
            Filter
          </Button>
        </div>
      </div>

      {/* Variables Content */}
      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="node" className="h-full flex flex-col">
          <TabsList className="mx-4 mt-2 mb-4">
            <TabsTrigger value="node" className="flex items-center space-x-2">
              <Settings className="w-4 h-4" />
              <span>Node Variables</span>
            </TabsTrigger>
            <TabsTrigger value="workflow" className="flex items-center space-x-2">
              <Globe className="w-4 h-4" />
              <span>Workflow Variables</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="node" className="flex-1 overflow-auto px-4 m-0">
            {/* Node Selection */}
            <div className="mb-4">
              <label className="text-xs font-medium text-muted-foreground mb-2 block">
                Selected Node
              </label>
              <select
                value={selectedNodeId}
                onChange={(e) => setSelectedNodeId(e.target.value)}
                className="w-full p-2 border rounded-md text-sm"
              >
                {Object.keys(mockNodeVariables).map(nodeId => (
                  <option key={nodeId} value={nodeId}>
                    {nodeId} ({mockNodeVariables[nodeId].length} variables)
                  </option>
                ))}
              </select>
            </div>

            {/* Node Variables Table */}
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8"></TableHead>
                    <TableHead>Variable</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Data Type</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead className="w-20">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredNodeVariables.map((variable) => (
                    <React.Fragment key={variable.id}>
                      <TableRow>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleRowExpansion(variable.id)}
                            className="p-0 h-6 w-6"
                          >
                            {expandedRows[variable.id] ? 
                              <ChevronDown className="w-4 h-4" /> : 
                              <ChevronRight className="w-4 h-4" />
                            }
                          </Button>
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-sm">{variable.name}</span>
                          {variable.description && (
                            <span className="block text-xs text-muted-foreground">
                              {variable.description}
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge className={getTypeBadgeColor(variable.type)}>
                            {variable.type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{variable.dataType}</Badge>
                        </TableCell>
                        <TableCell className="max-w-xs truncate font-mono text-xs">
                          {formatValue(variable.value, variable.dataType)}
                        </TableCell>
                        <TableCell className="flex items-center space-x-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => copyValue(variable.value)}
                            className="p-0 h-6 w-6"
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleRowExpansion(variable.id)}
                            className="p-0 h-6 w-6"
                          >
                            <Eye className="w-3 h-3" />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedRows[variable.id] && (
                        <TableRow>
                          <TableCell colSpan={6} className="bg-muted/50 p-3">
                            <pre className="text-xs bg-background p-3 rounded border overflow-auto max-h-40">
                              {formatValue(variable.value, variable.dataType)}
                            </pre>
                            <span className="block mt-2 text-xs text-muted-foreground">
                              Last updated: {new Date(variable.timestamp).toLocaleString()}
                            </span>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          <TabsContent value="workflow" className="flex-1 overflow-auto px-4 m-0">
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8"></TableHead>
                    <TableHead>Variable</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Data Type</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead className="w-20">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredWorkflowVariables.map((variable) => (
                    <React.Fragment key={variable.id}>
                      <TableRow>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleRowExpansion(variable.id)}
                            className="p-0 h-6 w-6"
                          >
                            {expandedRows[variable.id] ? 
                              <ChevronDown className="w-4 h-4" /> : 
                              <ChevronRight className="w-4 h-4" />
                            }
                          </Button>
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-sm">{variable.name}</span>
                          {variable.description && (
                            <span className="block text-xs text-muted-foreground">
                              {variable.description}
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge className={getTypeBadgeColor(variable.type)}>
                            {variable.type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{variable.dataType}</Badge>
                        </TableCell>
                        <TableCell>
                          {editingVariable === variable.id ? (
                            <>
                              <Input
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="h-8 text-xs font-mono inline-block w-32"
                              />
                              <Button variant="ghost" size="sm" onClick={saveEdit} className="p-0 h-6 w-6 ml-1">
                                <Save className="w-3 h-3" />
                              </Button>
                              <Button variant="ghost" size="sm" onClick={cancelEdit} className="p-0 h-6 w-6 ml-1">
                                <X className="w-3 h-3" />
                              </Button>
                            </>
                          ) : (
                            <span className="max-w-xs truncate font-mono text-xs">
                              {formatValue(variable.value, variable.dataType)}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="flex items-center space-x-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => copyValue(variable.value)}
                            className="p-0 h-6 w-6"
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          {variable.isEditable && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => startEditing(variable)}
                              className="p-0 h-6 w-6"
                            >
                              <Edit3 className="w-3 h-3" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleRowExpansion(variable.id)}
                            className="p-0 h-6 w-6"
                          >
                            <Eye className="w-3 h-3" />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedRows[variable.id] && (
                        <TableRow>
                          <TableCell colSpan={6} className="bg-muted/50 p-3">
                            <pre className="text-xs bg-background p-3 rounded border overflow-auto max-h-40">
                              {formatValue(variable.value, variable.dataType)}
                            </pre>
                            <span className="block mt-2 text-xs text-muted-foreground">
                              Last modified: {new Date(variable.lastModified).toLocaleString()}
                            </span>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default WorkflowVariables;
