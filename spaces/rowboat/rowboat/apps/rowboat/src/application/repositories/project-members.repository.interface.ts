import { ProjectMember } from "@/src/entities/models/project-member";
import { PaginatedList } from "@/src/entities/common/paginated-list";
import { z } from "zod";

export const CreateProjectMemberSchema = ProjectMember.pick({
    userId: true,
    projectId: true,
});

export interface IProjectMembersRepository {
    /**
     * Creates a new project member association. If the association already exists, returns the existing member.
     * @param data - The data required to create a project member (userId and projectId).
     * @returns A promise that resolves to the created or existing ProjectMember object.
     */
    create(data: z.infer<typeof CreateProjectMemberSchema>): Promise<z.infer<typeof ProjectMember>>;

    /**
     * Finds all project memberships for a given user, returned as a paginated list.
     * @param userId - The ID of the user whose project memberships are to be retrieved.
     * @returns A promise that resolves to a paginated list of ProjectMember objects.
     */
    findByUserId(userId: string, cursor?: string, limit?: number): Promise<z.infer<ReturnType<typeof PaginatedList<typeof ProjectMember>>>>;

    /**
     * Deletes all project member associations for a given project.
     * @param projectId - The ID of the project whose member associations should be deleted.
     * @returns A promise that resolves when the operation is complete.
     */
    deleteByProjectId(projectId: string): Promise<void>;

    /**
     * Checks if a specific membership exists.
     * @param projectId - The ID of the project.
     * @param userId - The ID of the user.
     * @returns A promise that resolves to true if the user is a member of the project, false otherwise.
     */
    exists(projectId: string, userId: string): Promise<boolean>;
}