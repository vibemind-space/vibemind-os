---
name: auth-setup
description: Implements authentication (JWT, OAuth2) and authorization (RBAC) from requirements
trigger_events: [CONTRACTS_GENERATED, AUTH_REQUIRED, ROLE_DEFINITION_NEEDED]
---

# Authentication & Authorization Setup Skill

## Purpose

Implement complete authentication and authorization systems from requirements.
This skill handles JWT tokens, OAuth2 providers, session management, and
Role-Based Access Control (RBAC) with proper security practices.

## Supported Patterns

| Pattern | Use Case | Security Level |
|---------|----------|----------------|
| **JWT** | Stateless API auth | High |
| **OAuth2** | Social login (Google, GitHub) | High |
| **RBAC** | Role-based permissions | High |
| **Session** | SSR applications | Medium |

## Trigger Events

| Event | Action |
|-------|--------|
| `CONTRACTS_GENERATED` | Detect auth requirements, setup basic auth |
| `AUTH_REQUIRED` | Implement specific auth mechanism |
| `ROLE_DEFINITION_NEEDED` | Setup RBAC roles and permissions |

## Authentication Setup

### 1. JWT Implementation

**File: `src/lib/auth/jwt.ts`**

```typescript
import jwt from "jsonwebtoken";
import { cookies } from "next/headers";

const JWT_SECRET = process.env.JWT_SECRET!;
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || "7d";
const REFRESH_TOKEN_EXPIRES_IN = "30d";

if (!JWT_SECRET) {
  throw new Error("JWT_SECRET environment variable is required");
}

export interface JWTPayload {
  userId: string;
  email: string;
  role: string;
  permissions: string[];
  iat?: number;
  exp?: number;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export function generateTokens(payload: Omit<JWTPayload, "iat" | "exp">): TokenPair {
  const accessToken = jwt.sign(payload, JWT_SECRET, {
    expiresIn: JWT_EXPIRES_IN,
  });

  const refreshToken = jwt.sign(
    { userId: payload.userId, type: "refresh" },
    JWT_SECRET,
    { expiresIn: REFRESH_TOKEN_EXPIRES_IN }
  );

  const decoded = jwt.decode(accessToken) as JWTPayload;
  const expiresIn = decoded.exp! - Math.floor(Date.now() / 1000);

  return { accessToken, refreshToken, expiresIn };
}

export function verifyToken(token: string): JWTPayload {
  try {
    return jwt.verify(token, JWT_SECRET) as JWTPayload;
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      throw new AuthError("Token expired", "TOKEN_EXPIRED");
    }
    if (error instanceof jwt.JsonWebTokenError) {
      throw new AuthError("Invalid token", "INVALID_TOKEN");
    }
    throw error;
  }
}

export function verifyRefreshToken(token: string): { userId: string } {
  const payload = jwt.verify(token, JWT_SECRET) as any;
  if (payload.type !== "refresh") {
    throw new AuthError("Invalid refresh token", "INVALID_REFRESH_TOKEN");
  }
  return { userId: payload.userId };
}

export class AuthError extends Error {
  constructor(
    message: string,
    public code: string
  ) {
    super(message);
    this.name = "AuthError";
  }
}
```

### 2. Password Hashing

**File: `src/lib/auth/password.ts`**

```typescript
import bcrypt from "bcryptjs";

const SALT_ROUNDS = 12;

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, SALT_ROUNDS);
}

export async function verifyPassword(
  password: string,
  hashedPassword: string
): Promise<boolean> {
  return bcrypt.compare(password, hashedPassword);
}

export function validatePasswordStrength(password: string): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (password.length < 8) {
    errors.push("Password must be at least 8 characters");
  }
  if (!/[A-Z]/.test(password)) {
    errors.push("Password must contain at least one uppercase letter");
  }
  if (!/[a-z]/.test(password)) {
    errors.push("Password must contain at least one lowercase letter");
  }
  if (!/[0-9]/.test(password)) {
    errors.push("Password must contain at least one number");
  }
  if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
    errors.push("Password must contain at least one special character");
  }

  return { valid: errors.length === 0, errors };
}
```

### 3. Auth API Routes

**File: `src/app/api/auth/register/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { hashPassword, validatePasswordStrength } from "@/lib/auth/password";
import { generateTokens } from "@/lib/auth/jwt";
import { z } from "zod";

const registerSchema = z.object({
  email: z.string().email("Invalid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  name: z.string().min(1, "Name is required"),
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const validation = registerSchema.safeParse(body);
    if (!validation.success) {
      return NextResponse.json(
        { error: "Validation Error", details: validation.error.flatten().fieldErrors },
        { status: 400 }
      );
    }

    const { email, password, name } = validation.data;

    // Validate password strength
    const passwordCheck = validatePasswordStrength(password);
    if (!passwordCheck.valid) {
      return NextResponse.json(
        { error: "Weak Password", details: { password: passwordCheck.errors } },
        { status: 400 }
      );
    }

    // Check if email exists
    const existingUser = await prisma.user.findUnique({
      where: { email },
    });

    if (existingUser) {
      return NextResponse.json(
        { error: "Conflict", message: "Email already registered" },
        { status: 409 }
      );
    }

    // Hash password and create user
    const hashedPassword = await hashPassword(password);

    const user = await prisma.user.create({
      data: {
        email,
        name,
        passwordHash: hashedPassword,
        role: "USER",
      },
      select: {
        id: true,
        email: true,
        name: true,
        role: true,
      },
    });

    // Get permissions for role
    const permissions = await getPermissionsForRole(user.role);

    // Generate tokens
    const tokens = generateTokens({
      userId: user.id,
      email: user.email,
      role: user.role,
      permissions,
    });

    return NextResponse.json({
      user,
      ...tokens,
    }, { status: 201 });
  } catch (error) {
    console.error("Registration error:", error);
    return NextResponse.json(
      { error: "Internal Server Error" },
      { status: 500 }
    );
  }
}
```

**File: `src/app/api/auth/login/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { verifyPassword } from "@/lib/auth/password";
import { generateTokens } from "@/lib/auth/jwt";
import { z } from "zod";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const validation = loginSchema.safeParse(body);
    if (!validation.success) {
      return NextResponse.json(
        { error: "Validation Error", details: validation.error.flatten().fieldErrors },
        { status: 400 }
      );
    }

    const { email, password } = validation.data;

    // Find user by email
    const user = await prisma.user.findUnique({
      where: { email },
      select: {
        id: true,
        email: true,
        name: true,
        role: true,
        passwordHash: true,
      },
    });

    if (!user) {
      return NextResponse.json(
        { error: "Unauthorized", message: "Invalid credentials" },
        { status: 401 }
      );
    }

    // Verify password
    const isValid = await verifyPassword(password, user.passwordHash);

    if (!isValid) {
      return NextResponse.json(
        { error: "Unauthorized", message: "Invalid credentials" },
        { status: 401 }
      );
    }

    // Get permissions for role
    const permissions = await getPermissionsForRole(user.role);

    // Generate tokens
    const tokens = generateTokens({
      userId: user.id,
      email: user.email,
      role: user.role,
      permissions,
    });

    // Remove passwordHash from response
    const { passwordHash: _, ...userWithoutPassword } = user;

    return NextResponse.json({
      user: userWithoutPassword,
      ...tokens,
    });
  } catch (error) {
    console.error("Login error:", error);
    return NextResponse.json(
      { error: "Internal Server Error" },
      { status: 500 }
    );
  }
}
```

**File: `src/app/api/auth/refresh/route.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { verifyRefreshToken, generateTokens, AuthError } from "@/lib/auth/jwt";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { refreshToken } = body;

    if (!refreshToken) {
      return NextResponse.json(
        { error: "Bad Request", message: "Refresh token required" },
        { status: 400 }
      );
    }

    // Verify refresh token
    const { userId } = verifyRefreshToken(refreshToken);

    // Get user
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        email: true,
        role: true,
      },
    });

    if (!user) {
      return NextResponse.json(
        { error: "Unauthorized", message: "User not found" },
        { status: 401 }
      );
    }

    // Get permissions and generate new tokens
    const permissions = await getPermissionsForRole(user.role);
    const tokens = generateTokens({
      userId: user.id,
      email: user.email,
      role: user.role,
      permissions,
    });

    return NextResponse.json(tokens);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json(
        { error: "Unauthorized", message: error.message, code: error.code },
        { status: 401 }
      );
    }
    console.error("Refresh error:", error);
    return NextResponse.json(
      { error: "Internal Server Error" },
      { status: 500 }
    );
  }
}
```

## Authorization (RBAC)

### 1. Role & Permission Definition

**File: `src/lib/auth/rbac.ts`**

```typescript
// Permission definitions
export enum Permission {
  // User permissions
  READ_USERS = "users:read",
  CREATE_USERS = "users:create",
  UPDATE_USERS = "users:update",
  DELETE_USERS = "users:delete",

  // Post permissions
  READ_POSTS = "posts:read",
  CREATE_POSTS = "posts:create",
  UPDATE_POSTS = "posts:update",
  DELETE_POSTS = "posts:delete",
  PUBLISH_POSTS = "posts:publish",

  // Admin permissions
  MANAGE_ROLES = "roles:manage",
  VIEW_ANALYTICS = "analytics:view",
  SYSTEM_ADMIN = "system:admin",
}

// Role definitions with permissions
export const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  ADMIN: [
    Permission.SYSTEM_ADMIN,
    Permission.MANAGE_ROLES,
    Permission.VIEW_ANALYTICS,
    Permission.READ_USERS,
    Permission.CREATE_USERS,
    Permission.UPDATE_USERS,
    Permission.DELETE_USERS,
    Permission.READ_POSTS,
    Permission.CREATE_POSTS,
    Permission.UPDATE_POSTS,
    Permission.DELETE_POSTS,
    Permission.PUBLISH_POSTS,
  ],
  MANAGER: [
    Permission.READ_USERS,
    Permission.CREATE_USERS,
    Permission.UPDATE_USERS,
    Permission.VIEW_ANALYTICS,
    Permission.READ_POSTS,
    Permission.CREATE_POSTS,
    Permission.UPDATE_POSTS,
    Permission.PUBLISH_POSTS,
  ],
  USER: [
    Permission.READ_USERS,
    Permission.READ_POSTS,
    Permission.CREATE_POSTS,
    Permission.UPDATE_POSTS, // Only own posts (checked at resource level)
    Permission.DELETE_POSTS, // Only own posts
  ],
  GUEST: [
    Permission.READ_POSTS,
  ],
};

export async function getPermissionsForRole(role: string): Promise<string[]> {
  return ROLE_PERMISSIONS[role] || [];
}

export function hasPermission(
  userPermissions: string[],
  requiredPermission: Permission
): boolean {
  // System admin has all permissions
  if (userPermissions.includes(Permission.SYSTEM_ADMIN)) {
    return true;
  }
  return userPermissions.includes(requiredPermission);
}

export function hasAnyPermission(
  userPermissions: string[],
  requiredPermissions: Permission[]
): boolean {
  return requiredPermissions.some((p) => hasPermission(userPermissions, p));
}

export function hasAllPermissions(
  userPermissions: string[],
  requiredPermissions: Permission[]
): boolean {
  return requiredPermissions.every((p) => hasPermission(userPermissions, p));
}
```

### 2. Permission Middleware

**File: `src/lib/auth/middleware.ts`**

```typescript
import { NextRequest, NextResponse } from "next/server";
import { verifyToken, AuthError } from "./jwt";
import { Permission, hasPermission } from "./rbac";

export type AuthenticatedRequest = NextRequest & {
  user: {
    userId: string;
    email: string;
    role: string;
    permissions: string[];
  };
};

export function withAuth(
  handler: (req: AuthenticatedRequest) => Promise<NextResponse>,
  options?: { permissions?: Permission[] }
) {
  return async (req: NextRequest): Promise<NextResponse> => {
    try {
      // Get token from header
      const authHeader = req.headers.get("Authorization");
      if (!authHeader?.startsWith("Bearer ")) {
        return NextResponse.json(
          { error: "Unauthorized", message: "Missing authentication token" },
          { status: 401 }
        );
      }

      const token = authHeader.substring(7);
      const payload = verifyToken(token);

      // Check permissions if required
      if (options?.permissions) {
        const hasRequiredPermission = options.permissions.some((p) =>
          hasPermission(payload.permissions, p)
        );

        if (!hasRequiredPermission) {
          return NextResponse.json(
            { error: "Forbidden", message: "Insufficient permissions" },
            { status: 403 }
          );
        }
      }

      // Add user to request
      const authReq = req as AuthenticatedRequest;
      authReq.user = payload;

      return handler(authReq);
    } catch (error) {
      if (error instanceof AuthError) {
        return NextResponse.json(
          { error: "Unauthorized", message: error.message, code: error.code },
          { status: 401 }
        );
      }
      throw error;
    }
  };
}

// Helper for resource ownership check
export function isOwner(userId: string, resourceOwnerId: string): boolean {
  return userId === resourceOwnerId;
}
```

### 3. Protected Route Example

**File: `src/app/api/admin/users/route.ts`**

```typescript
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { withAuth, AuthenticatedRequest } from "@/lib/auth/middleware";
import { Permission } from "@/lib/auth/rbac";

// Only users with MANAGE_ROLES permission can access
export const GET = withAuth(
  async (req: AuthenticatedRequest) => {
    const users = await prisma.user.findMany({
      select: {
        id: true,
        email: true,
        name: true,
        role: true,
        createdAt: true,
      },
    });

    return NextResponse.json(users);
  },
  { permissions: [Permission.MANAGE_ROLES] }
);
```

## OAuth2 Integration

### 1. NextAuth.js Setup

**File: `src/lib/auth/next-auth.ts`**

```typescript
import { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import GitHubProvider from "next-auth/providers/github";
import CredentialsProvider from "next-auth/providers/credentials";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";
import { verifyPassword } from "./password";
import { getPermissionsForRole } from "./rbac";

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma),
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GitHubProvider({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          throw new Error("Invalid credentials");
        }

        const user = await prisma.user.findUnique({
          where: { email: credentials.email },
        });

        if (!user || !user.passwordHash) {
          throw new Error("Invalid credentials");
        }

        const isValid = await verifyPassword(
          credentials.password,
          user.passwordHash
        );

        if (!isValid) {
          throw new Error("Invalid credentials");
        }

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          role: user.role,
        };
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.userId = user.id;
        token.role = user.role || "USER";
        token.permissions = await getPermissionsForRole(token.role as string);
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.userId as string;
        session.user.role = token.role as string;
        session.user.permissions = token.permissions as string[];
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
};
```

## React Auth Hook

**File: `src/hooks/useAuth.ts`**

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  refreshAuth: () => Promise<void>;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email: string, password: string) => {
        set({ isLoading: true });
        try {
          const response = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || "Login failed");
          }

          const data = await response.json();
          set({
            user: data.user,
            accessToken: data.accessToken,
            refreshToken: data.refreshToken,
            isAuthenticated: true,
          });
        } finally {
          set({ isLoading: false });
        }
      },

      register: async (email: string, password: string, name: string) => {
        set({ isLoading: true });
        try {
          const response = await fetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password, name }),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || "Registration failed");
          }

          const data = await response.json();
          set({
            user: data.user,
            accessToken: data.accessToken,
            refreshToken: data.refreshToken,
            isAuthenticated: true,
          });
        } finally {
          set({ isLoading: false });
        }
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        });
      },

      refreshAuth: async () => {
        const { refreshToken } = get();
        if (!refreshToken) return;

        try {
          const response = await fetch("/api/auth/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refreshToken }),
          });

          if (!response.ok) {
            get().logout();
            return;
          }

          const data = await response.json();
          set({
            accessToken: data.accessToken,
            refreshToken: data.refreshToken,
          });
        } catch {
          get().logout();
        }
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
```

## Prisma Schema Extension

```prisma
model User {
  id           String    @id @default(uuid())
  email        String    @unique
  name         String
  passwordHash String?
  role         String    @default("USER")
  accounts     Account[]
  sessions     Session[]
  createdAt    DateTime  @default(now())
  updatedAt    DateTime  @updatedAt
}

model Account {
  id                String  @id @default(uuid())
  userId            String
  type              String
  provider          String
  providerAccountId String
  refresh_token     String? @db.Text
  access_token      String? @db.Text
  expires_at        Int?
  token_type        String?
  scope             String?
  id_token          String? @db.Text
  session_state     String?

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([provider, providerAccountId])
}

model Session {
  id           String   @id @default(uuid())
  sessionToken String   @unique
  userId       String
  expires      DateTime
  user         User     @relation(fields: [userId], references: [id], onDelete: Cascade)
}
```

## Admin User Seeding (CRITICAL)

Every authentication system MUST include admin seeding at startup to avoid bootstrap problems.

### FastAPI Example

**File: `src/api/main.py`** (add to startup event)

```python
@app.on_event("startup")
async def seed_admin_user():
    """Seed a default admin user for testing/bootstrap purposes."""
    from src.api.dependencies import get_auth_service, get_user_service
    from src.models.user import UserStatus, UserInDB
    import uuid

    auth_service = get_auth_service()
    user_service = get_user_service()

    # Check if admin already exists
    admin_username = "admin"
    for user in auth_service._users.values():
        if user.username == admin_username:
            print(f"[Startup] Admin user '{admin_username}' already exists")
            return

    # Create admin user with ACTIVE status and full permissions
    admin_id = str(uuid.uuid4())
    admin_user = UserInDB(
        id=admin_id,
        email="admin@system.example.com",
        username=admin_username,
        full_name="System Administrator",
        hashed_password=auth_service.hash_password("Admin123!@#"),
        status=UserStatus.ACTIVE,
        roles=["admin", "super_admin"],
        permissions={"*:*"},  # Wildcard grants all permissions
        email_verified=True,
        failed_login_attempts=0,
        # ... other required fields
    )

    auth_service._users[admin_id] = admin_user
    user_service._users[admin_id] = admin_user
    print(f"[Startup] Created admin user: {admin_username}")
```

### Next.js/Prisma Example

**File: `prisma/seed.ts`**

```typescript
// Load env vars for DATABASE_URL
import 'dotenv/config';
import { PrismaClient } from "@prisma/client";
import { hashPassword } from "@/lib/auth/password";

const prisma = new PrismaClient();

async function main() {
  // Check if admin exists
  const existingAdmin = await prisma.user.findUnique({
    where: { email: "admin@system.example.com" },
  });

  if (!existingAdmin) {
    const hashedPassword = await hashPassword("Admin123!@#");
    await prisma.user.create({
      data: {
        email: "admin@system.example.com",
        name: "System Administrator",
        passwordHash: hashedPassword,
        role: "ADMIN",
        emailVerified: new Date(), // Already verified
      },
    });
    console.log("[Seed] Created admin user");
  }
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
```

### CRITICAL Requirements for Admin Seeding:
- [x] Admin user MUST have ACTIVE status (not pending_verification)
- [x] Admin user MUST have email_verified = true
- [x] Admin user MUST have `*:*` or full permission set
- [x] Seeding MUST be idempotent (check if exists first)
- [x] Default password MUST meet password policy requirements

## Permission Checking (CRITICAL)

Permission checks MUST include BOTH role-based AND direct user permissions.

### FastAPI Example

**File: `src/api/dependencies.py`**

```python
class RequirePermission:
    async def __call__(
        self,
        current_user: UserInDB = Depends(get_current_active_user),
        role_service: RoleService = Depends(get_role_service),
    ) -> UserInDB:
        # Collect all permissions
        user_permissions: Set[str] = set()

        # CRITICAL: First add user's DIRECT permissions if any
        if hasattr(current_user, 'permissions') and current_user.permissions:
            user_permissions.update(current_user.permissions)

        # Then add permissions from roles
        for role_id in current_user.roles:
            role_perms = await role_service.get_role_permissions(role_id, include_inherited=True)
            user_permissions.update(role_perms)

        # Check permission with wildcard support
        if self.permission not in user_permissions:
            resource = self.permission.split(":")[0] if ":" in self.permission else self.permission
            wildcard = f"{resource}:*"
            admin_wildcard = "*:*"

            if wildcard not in user_permissions and admin_wildcard not in user_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {self.permission} required"
                )

        return current_user
```

### TypeScript/Next.js Example

```typescript
export function hasPermission(
  userPermissions: string[],
  requiredPermission: Permission | string
): boolean {
  // Check for admin wildcard
  if (userPermissions.includes("*:*")) {
    return true;
  }

  // Check for resource wildcard (e.g., "users:*" matches "users:read")
  const resource = requiredPermission.split(":")[0];
  if (userPermissions.includes(`${resource}:*`)) {
    return true;
  }

  // Direct permission check
  return userPermissions.includes(requiredPermission);
}
```

### CRITICAL Requirements for Permission Checking:
- [x] Check user.permissions DIRECTLY (not just from roles)
- [x] Support `*:*` wildcard for admin access
- [x] Support `resource:*` wildcards (e.g., `users:*`)
- [x] Include inherited permissions from role hierarchy
- [x] Return 403 Forbidden with clear error message

## Anti-Mock Policy

### NIEMALS generieren:
- [ ] Hardcoded Tokens oder Secrets
- [ ] Fake Password-Verification (return true)
- [ ] Mock JWT-Payloads
- [ ] Umgehung von Permission-Checks
- [ ] TODO-Kommentare in Security-Code
- [ ] Missing admin seeding (causes bootstrap problems)
- [ ] Permission checks that only use roles (must include direct permissions)

### IMMER generieren:
- [x] Echte JWT-Generierung mit Secret aus ENV
- [x] Bcrypt Password-Hashing
- [x] Vollständige Permission-Checks (direct + role-based)
- [x] Error-Handling für alle Auth-Flows
- [x] Sichere Token-Refresh-Logik
- [x] Admin user seeding at startup
- [x] Wildcard permission support (*:*)

## Output Files

```
output/src/
├── lib/
│   └── auth/
│       ├── jwt.ts            # JWT generation/verification
│       ├── password.ts       # Password hashing
│       ├── rbac.ts           # Role & permission definitions
│       ├── middleware.ts     # Auth middleware
│       └── next-auth.ts      # NextAuth.js config (if OAuth)
├── app/
│   └── api/
│       └── auth/
│           ├── register/route.ts
│           ├── login/route.ts
│           ├── logout/route.ts
│           ├── refresh/route.ts
│           └── [...nextauth]/route.ts  # If OAuth enabled
├── hooks/
│   └── useAuth.ts            # React auth hook
└── contexts/
    └── AuthContext.tsx       # Auth provider (optional)
```

## Environment Variables

```env
# JWT
JWT_SECRET=<generated-64-char-secret>
JWT_EXPIRES_IN=7d

# OAuth (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<generated-32-char-secret>
```

## Dependencies

```json
{
  "dependencies": {
    "jsonwebtoken": "^9.x",
    "bcryptjs": "^2.x",
    "next-auth": "^4.x",
    "@auth/prisma-adapter": "^1.x",
    "zustand": "^4.x"
  },
  "devDependencies": {
    "@types/jsonwebtoken": "^9.x",
    "@types/bcryptjs": "^2.x"
  }
}
```
