"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/markdown";
import { useWS, Question } from "@/components/ws-provider";
import { McpSelectionView } from "@/components/mcp-selection-view";
import { ToolAssignmentView } from "@/components/tool-assignment-view";
import { ArchitectureReviewView } from "@/components/architecture-review-view";
import { McpConfigView } from "@/components/mcp-config-view";
import { ApiKeyRequestView } from "@/components/api-key-request-view";

function QuestionContent({ question }: { question: Question }) {
  const { sendAnswer } = useWS();
  const [replyText, setReplyText] = useState("");
  const [showReply, setShowReply] = useState(question.type === "missing_info");

  const handleApprove = () => sendAnswer(question.id, "approve");
  const handleReject = () => sendAnswer(question.id, "reject");
  const handleReply = () => {
    if (replyText.trim()) {
      sendAnswer(question.id, "reply", replyText.trim());
    }
  };

  // Route to specialized views for new question types
  if (question.type === "mcp_selection") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <McpSelectionView question={question} />
      </>
    );
  }

  if (question.type === "tool_assignment") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <ToolAssignmentView question={question} />
      </>
    );
  }

  if (question.type === "architecture_review") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
          {question.todo_hint && <DialogDescription>{question.todo_hint}</DialogDescription>}
        </DialogHeader>
        <ArchitectureReviewView question={question} />
      </>
    );
  }

  if (question.type === "mcp_config") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <McpConfigView question={question} />
      </>
    );
  }

  if (question.type === "api_key_request") {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        </DialogHeader>
        <ApiKeyRequestView question={question} />
      </>
    );
  }

  const typeLabel = {
    missing_info: "Missing Information",
    implementation_choice: "Implementation Choice",
    approval: "Code Approval",
  }[question.type] || question.type;

  const typeColor = {
    missing_info: "bg-amber-500/20 text-amber-400",
    implementation_choice: "bg-blue-500/20 text-blue-400",
    approval: "bg-green-500/20 text-green-400",
  }[question.type] || "";

  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-2 mb-1">
          <Badge className={`${typeColor} border-0 text-xs`}>{typeLabel}</Badge>
          <code className="text-sm text-neutral-400 bg-neutral-800 px-2 py-0.5 rounded">
            {question.tool_name}
          </code>
        </div>
        <DialogTitle className="text-neutral-50">{question.message}</DialogTitle>
        {question.todo_hint && (
          <DialogDescription>TODO: {question.todo_hint}</DialogDescription>
        )}
      </DialogHeader>

      <div className="space-y-4 flex-1 overflow-y-auto">
        {question.mock_code && (
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-1">Current Mock</h4>
            <Markdown content={`\`\`\`python\n${question.mock_code}\n\`\`\``} />
          </div>
        )}

        {question.generated_code && (
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-1">Generated Implementation</h4>
            <Markdown content={`\`\`\`python\n${question.generated_code}\n\`\`\``} />
          </div>
        )}

        {question.type === "implementation_choice" && question.options.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-neutral-400">Options</h4>
            {question.options.map((opt, i) => (
              <Button
                key={i}
                variant="outline"
                className="w-full justify-start text-left"
                onClick={() => sendAnswer(question.id, "reply", opt)}
              >
                {opt}
              </Button>
            ))}
          </div>
        )}

        {(showReply || question.type === "missing_info") && (
          <div>
            <Textarea
              placeholder="Type your answer..."
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              className="bg-neutral-800 border-neutral-700 text-neutral-50 min-h-[80px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                  handleReply();
                }
              }}
            />
            <p className="text-xs text-neutral-500 mt-1">Ctrl+Enter to send</p>
          </div>
        )}
      </div>

      <DialogFooter>
        {question.type === "approval" && (
          <>
            <Button variant="outline" onClick={handleReject} className="border-red-800 text-red-400 hover:bg-red-950">
              Reject
            </Button>
            {!showReply && (
              <Button variant="outline" onClick={() => setShowReply(true)}>
                Reply
              </Button>
            )}
            {showReply && replyText.trim() && (
              <Button variant="outline" onClick={handleReply}>
                Send Reply
              </Button>
            )}
            <Button onClick={handleApprove} className="bg-green-600 hover:bg-green-700 text-white">
              Approve
            </Button>
          </>
        )}
        {question.type === "missing_info" && (
          <Button onClick={handleReply} disabled={!replyText.trim()} className="bg-blue-600 hover:bg-blue-700 text-white">
            Send Answer
          </Button>
        )}
        {question.type === "implementation_choice" && showReply && replyText.trim() && (
          <Button onClick={handleReply} className="bg-blue-600 hover:bg-blue-700 text-white">
            Send Custom Answer
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

export function QuestionModal() {
  const { questions } = useWS();
  const currentQuestion = questions[0] || null;

  return (
    <Dialog open={!!currentQuestion}>
      <DialogContent className="w-[95vw] max-w-[95vw] h-[90vh] max-h-[90vh] bg-neutral-900 border-neutral-700 text-neutral-50 flex flex-col" showCloseButton={false}>
        {currentQuestion && <QuestionContent question={currentQuestion} />}
      </DialogContent>
    </Dialog>
  );
}
