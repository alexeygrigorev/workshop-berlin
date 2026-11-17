export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.18"
  }
  public: {
    Tables: {
      ballots: {
        Row: {
          choices: string[]
          poll_id: string
          submitted_at: string
          team_id: string
          user_id: string
        }
        Insert: {
          choices: string[]
          poll_id: string
          submitted_at?: string
          team_id: string
          user_id: string
        }
        Update: {
          choices?: string[]
          poll_id?: string
          submitted_at?: string
          team_id?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "ballots_poll_id_fkey"
            columns: ["poll_id"]
            isOneToOne: false
            referencedRelation: "polls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ballots_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      poll_candidates: {
        Row: {
          poll_id: string
          restaurant_id: string
          team_id: string
        }
        Insert: {
          poll_id: string
          restaurant_id: string
          team_id: string
        }
        Update: {
          poll_id?: string
          restaurant_id?: string
          team_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "poll_candidates_poll_id_fkey"
            columns: ["poll_id"]
            isOneToOne: false
            referencedRelation: "polls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "poll_candidates_restaurant_id_fkey"
            columns: ["restaurant_id"]
            isOneToOne: false
            referencedRelation: "restaurants"
            referencedColumns: ["id"]
          },
        ]
      }
      poll_seeds: {
        Row: {
          poll_id: string
          seed: string
        }
        Insert: {
          poll_id: string
          seed: string
        }
        Update: {
          poll_id?: string
          seed?: string
        }
        Relationships: [
          {
            foreignKeyName: "poll_seeds_poll_id_fkey"
            columns: ["poll_id"]
            isOneToOne: true
            referencedRelation: "polls"
            referencedColumns: ["id"]
          },
        ]
      }
      polls: {
        Row: {
          ballot_count: number | null
          closes_at: string
          created_at: string
          final_scores: Json | null
          finalized_at: string | null
          id: string
          no_winner: boolean
          opens_at: string
          poll_date: string
          status: string
          team_id: string
          tie_break: string | null
          timezone: string
          winner_id: string | null
        }
        Insert: {
          ballot_count?: number | null
          closes_at: string
          created_at?: string
          final_scores?: Json | null
          finalized_at?: string | null
          id?: string
          no_winner?: boolean
          opens_at: string
          poll_date: string
          status?: string
          team_id: string
          tie_break?: string | null
          timezone: string
          winner_id?: string | null
        }
        Update: {
          ballot_count?: number | null
          closes_at?: string
          created_at?: string
          final_scores?: Json | null
          finalized_at?: string | null
          id?: string
          no_winner?: boolean
          opens_at?: string
          poll_date?: string
          status?: string
          team_id?: string
          tie_break?: string | null
          timezone?: string
          winner_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "polls_team_id_fkey"
            columns: ["team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "polls_winner_id_fkey"
            columns: ["winner_id"]
            isOneToOne: false
            referencedRelation: "restaurants"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          created_at: string
          display_name: string
          id: string
        }
        Insert: {
          created_at?: string
          display_name?: string
          id: string
        }
        Update: {
          created_at?: string
          display_name?: string
          id?: string
        }
        Relationships: []
      }
      restaurants: {
        Row: {
          address: string | null
          archived_at: string | null
          created_at: string
          created_by: string | null
          cuisine: string | null
          id: string
          map_url: string | null
          name: string
          normalized_name: string | null
          notes: string | null
          team_id: string
          website_url: string | null
        }
        Insert: {
          address?: string | null
          archived_at?: string | null
          created_at?: string
          created_by?: string | null
          cuisine?: string | null
          id?: string
          map_url?: string | null
          name: string
          normalized_name?: string | null
          notes?: string | null
          team_id: string
          website_url?: string | null
        }
        Update: {
          address?: string | null
          archived_at?: string | null
          created_at?: string
          created_by?: string | null
          cuisine?: string | null
          id?: string
          map_url?: string | null
          name?: string
          normalized_name?: string | null
          notes?: string | null
          team_id?: string
          website_url?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "restaurants_team_id_fkey"
            columns: ["team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
        ]
      }
      team_invites: {
        Row: {
          created_at: string
          created_by: string | null
          id: string
          revoked_at: string | null
          team_id: string
          token: string
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          id?: string
          revoked_at?: string | null
          team_id: string
          token?: string
        }
        Update: {
          created_at?: string
          created_by?: string | null
          id?: string
          revoked_at?: string | null
          team_id?: string
          token?: string
        }
        Relationships: [
          {
            foreignKeyName: "team_invites_team_id_fkey"
            columns: ["team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
        ]
      }
      team_members: {
        Row: {
          joined_at: string
          role: string
          team_id: string
          user_id: string
        }
        Insert: {
          joined_at?: string
          role?: string
          team_id: string
          user_id: string
        }
        Update: {
          joined_at?: string
          role?: string
          team_id?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "team_members_team_id_fkey"
            columns: ["team_id"]
            isOneToOne: false
            referencedRelation: "teams"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "team_members_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      teams: {
        Row: {
          close_time: string
          created_at: string
          created_by: string
          id: string
          name: string
          office_location: string | null
          open_time: string
          timezone: string
        }
        Insert: {
          close_time?: string
          created_at?: string
          created_by: string
          id?: string
          name: string
          office_location?: string | null
          open_time?: string
          timezone?: string
        }
        Update: {
          close_time?: string
          created_at?: string
          created_by?: string
          id?: string
          name?: string
          office_location?: string | null
          open_time?: string
          timezone?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      create_team: {
        Args: { _name: string; _office?: string; _timezone: string }
        Returns: string
      }
      ensure_today_poll: { Args: { _team: string }; Returns: string }
      finalize_poll: { Args: { _poll: string }; Returns: undefined }
      invite_info: {
        Args: { _token: string }
        Returns: {
          already_member: boolean
          team_id: string
          team_name: string
        }[]
      }
      is_team_admin: { Args: { _team: string }; Returns: boolean }
      is_team_member: { Args: { _team: string }; Returns: boolean }
      join_team: { Args: { _token: string }; Returns: string }
      reconcile_all_polls: { Args: never; Returns: undefined }
      regenerate_invite: { Args: { _team: string }; Returns: string }
      shares_team: { Args: { _user: string }; Returns: boolean }
      submit_ballot: {
        Args: { _choices: string[]; _poll: string }
        Returns: string
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
