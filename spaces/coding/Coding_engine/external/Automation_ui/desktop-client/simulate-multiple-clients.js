/**
 * Simulate Multiple Desktop Clients
 * Creates 3 virtual desktop clients to test multi-client UI
 */
import WebSocket from "ws";

const EDGE_FUNCTION_URL =
  process.env.SUPABASE_WS_URL || "ws://localhost:8007/ws/live-desktop";

// Define 3 simulated desktop clients
const simulatedClients = [
  {
    clientId: "desktop_main-workstation_abc123",
    hostname: "MAIN-WORKSTATION",
    monitors: [
      {
        index: 0,
        name: "Monitor 1",
        width: 2560,
        height: 1440,
        is_primary: true,
      },
      {
        index: 1,
        name: "Monitor 2",
        width: 1920,
        height: 1080,
        is_primary: false,
      },
    ],
  },
  {
    clientId: "desktop_laptop-x1carbon_def456",
    hostname: "LAPTOP-X1CARBON",
    monitors: [
      {
        index: 0,
        name: "Laptop Display",
        width: 1920,
        height: 1080,
        is_primary: true,
      },
    ],
  },
  {
    clientId: "desktop_gaming-pc_ghi789",
    hostname: "GAMING-PC",
    monitors: [
      {
        index: 0,
        name: "Left Monitor",
        width: 1920,
        height: 1080,
        is_primary: false,
      },
      {
        index: 1,
        name: "Center Monitor",
        width: 2560,
        height: 1440,
        is_primary: true,
      },
      {
        index: 2,
        name: "Right Monitor",
        width: 1920,
        height: 1080,
        is_primary: false,
      },
    ],
  },
];

// Create colored test frames
function createColoredFrame(color, clientId, monitorIndex) {
  // Create a small colored square as JPEG base64
  const colors = {
    red: "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA//2Q==",
    green:
      "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJMAAA//2Q==",
    blue: "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAr/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCuAAD/2Q==",
  };

  // Use different colors for different clients
  const clientColors = ["red", "green", "blue"];
  const colorIndex =
    simulatedClients.findIndex((c) => c.clientId === clientId) %
    clientColors.length;

  return colors[clientColors[colorIndex]];
}

// Connect each simulated client
const connections = simulatedClients.map((client, clientIndex) => {
  console.log(`\n[${clientIndex + 1}] Connecting: ${client.hostname}`);
  console.log(`    Client ID: ${client.clientId}`);
  console.log(`    Monitors: ${client.monitors.length}`);

  const wsUrl = `${EDGE_FUNCTION_URL}?client_type=desktop&client_id=${client.clientId}`;
  const ws = new WebSocket(wsUrl);

  let frameCount = 0;

  ws.on("open", () => {
    console.log(`[${clientIndex + 1}] ✅ Connected: ${client.hostname}`);

    // Send handshake
    const handshake = {
      type: "handshake",
      clientInfo: {
        clientType: "desktop",
        clientId: client.clientId,
        hostname: client.hostname,
        platform: "Windows",
        capabilities: ["screen_capture", "multi_monitor"],
        monitors: client.monitors,
      },
      timestamp: new Date().toISOString(),
    };

    ws.send(JSON.stringify(handshake));
    console.log(`[${clientIndex + 1}] 📤 Handshake sent`);

    // Start sending frames for all monitors
    const frameInterval = setInterval(() => {
      client.monitors.forEach((monitor) => {
        const monitorId = `monitor_${monitor.index}`;

        const frame = {
          type: "frame_data",
          frameData: createColoredFrame(null, client.clientId, monitor.index),
          frameNumber: frameCount,
          timestamp: new Date().toISOString(),
          monitorId: monitorId,
          width: monitor.width,
          height: monitor.height,
          metadata: {
            monitorId: monitorId,
            monitorIndex: monitor.index,
            width: monitor.width,
            height: monitor.height,
            format: "jpeg",
            quality: 80,
          },
        };

        ws.send(JSON.stringify(frame));
      });

      frameCount++;

      if (frameCount % 50 === 0) {
        console.log(
          `[${clientIndex + 1}] 📺 ${client.hostname}: ${frameCount} frames sent`,
        );
      }
    }, 100); // 10 fps

    // Store interval for cleanup
    ws.frameInterval = frameInterval;
  });

  ws.on("message", (data) => {
    try {
      const message = JSON.parse(data.toString());

      switch (message.type) {
        case "handshake_ack":
          console.log(`[${clientIndex + 1}] ✅ Handshake acknowledged`);
          break;
        case "start_capture":
          console.log(
            `[${clientIndex + 1}] 📬 Received start_capture for ${message.monitorId}`,
          );
          break;
        case "stop_capture":
          console.log(
            `[${clientIndex + 1}] 📬 Received stop_capture for ${message.monitorId}`,
          );
          break;
      }
    } catch (error) {
      // Ignore parse errors
    }
  });

  ws.on("error", (error) => {
    console.error(
      `[${clientIndex + 1}] ❌ Error (${client.hostname}):`,
      error.message,
    );
  });

  ws.on("close", () => {
    console.log(`[${clientIndex + 1}] 🔌 Disconnected: ${client.hostname}`);
    if (ws.frameInterval) {
      clearInterval(ws.frameInterval);
    }
  });

  return { client, ws };
});

console.log("\n=================================================");
console.log("🎬 Simulating 3 Desktop Clients:");
console.log("   1. MAIN-WORKSTATION (2 monitors)");
console.log("   2. LAPTOP-X1CARBON (1 monitor)");
console.log("   3. GAMING-PC (3 monitors)");
console.log("=================================================");
console.log("\n📺 Total: 6 monitor streams");
console.log("\n🌐 Open browser: http://localhost:5173/multi-desktop");
console.log("   You should see a 6-panel grid!\n");
console.log("Press Ctrl+C to stop\n");

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n\n🛑 Shutting down...");
  connections.forEach(({ client, ws }) => {
    if (ws.frameInterval) {
      clearInterval(ws.frameInterval);
    }
    ws.close();
  });
  process.exit(0);
});
